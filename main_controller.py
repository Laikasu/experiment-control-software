from PySide6.QtCore import QObject, Signal, QThread, QMutex, QWaitCondition, Qt, QSettings
from PySide6.QtWidgets import QFileDialog

import time
import numpy as np

import os
import tifffile as tiff
import cv2
import yaml

import processing as pc

from controllers import StageController, PumpController, LaserController, CameraController
from widgets import SweepDialog, PropertiesDialog

class PersistentWorkerThread(QThread):
    def __init__(self, func):
        super().__init__()
        self.func = func


class AquisitionWorkerThread(QThread):
        done = Signal()
        def __init__(self, parent, func, *args):
            super().__init__(parent)
            self.args = args
            self.photos = []
            self.func = func
            self.parent = parent
            
            parent.cancel_aquisition_act.triggered.connect(self.terminate)

        def run(self):
            self.func(*self.args)
            self.done.emit()


class MainController(QObject):
    update_controls = Signal()
    update_background = Signal(np.ndarray)
    def __init__(self, ):
        super().__init__()

        # Setup devices
        self.stage = StageController()
        self.pump = PumpController(self)
        self.laser = LaserController(self)
        self.camera = CameraController(self)

        # Routes
        self.pump.changedState.connect(self.update_controls)
        self.laser.changedState.connect(self.update_controls)


        self.shot_count = 10 # Shoot 10 images to average over

        self.got_image_mutex = QMutex()
        self.got_image = QWaitCondition()
        self.aquiring = False
        self.aquiring_mutex = QMutex()

        # Load settings
        self.settings = QSettings('Casper', 'Monitor')


        if self.settings.contains('magnification') and self.settings.contains('pxsize'):
            self.magnification = self.settings.value('magnification', type=int)
            self.pxsize = self.settings.value('pxsize', type=float)
        else:
            self.magnification = 60 # Default
            self.pxsize = 3.45
            self.settings = QSettings('Casper', 'Monitor')
            self.set_setup_parameters()

    def set_setup_parameters(self):
        dialog = PropertiesDialog(self.magnification, self.pxsize)
        if dialog.exec():
            self.magnification, self.pxsize = dialog.get_values()
            self.settings.setValue('magnification', self.magnification)
            self.settings.setValue('pxsize', self.pxsize)
    

    # =====================================================
    # =================   Actions   =======================
    # =====================================================


    def take_z_sweep(self, *actions):
        """Move to different defocus then perform next action"""
        z_zero = self.stage.get_z_position()
        for i, z in enumerate(self.z_positions*10/1.4):
            # Set position
            pos = z_zero + z
            self.z_position = i
            self.stage.set_z_position(z)
            time.sleep(2)
            # Next action
            self.action(*actions)

        # Reset
        self.stage.set_z_position(z_zero)


    def take_laser_sweep(self, *actions):
        """Move to different wavelen then perform next action"""
        init_wavelen = self.laser.wavelen()
        self.laser.set_wavelen(self.wavelens[0])
        time.sleep(5)
        self.laser_data_raw = []
        for i, wavelen in enumerate(self.wavelens):
            self.laser.set_wavelen(wavelen)
            time.sleep(0.5)
            # Take next action
            self.action(*actions)
        
        # Reset laser
        self.laser.set_wavelen(init_wavelen)
    

    def take_media_sweep(self, *actions):
        """Move to medium and then perform next action"""

        input = self.media

        # Take a picture once a second, storing it in media_data_raw
        self.media_data_raw = []

        self.pump.wait_till_ready()
        for medium in input:
            self.pump.pickup(medium)
            self.pump.flow()
            self.pump.wait_till_ready()
            self.action(*actions)
            time.sleep(2)
    

    # Image taking

    def take_single(self):
        """Take a single photo and store it"""
        self.camera.new_frame.connect(self.store_image, Qt.ConnectionType.SingleShotConnection)
        self.got_image_mutex.lock()
        # Retry
        while not self.got_image.wait(self.got_image_mutex, 1000):
            self.camera.new_frame.connect(self.store_image, Qt.ConnectionType.SingleShotConnection)
        self.got_image_mutex.unlock()

    def take_single_avg(self):
        """Take a single averaged photo and store it"""
        for i in range(self.shot_count):
            self.take_single()


    def take_sequence(self):
        """Take a grid photo and store it"""
        distance = 4
        positions = np.array([[1,0], [1,1], [0,1]])*distance
        anchor = np.array(self.stage.get_xy_position())

        self.take_single()
            
        for i, position in enumerate(positions):
            pos = position + anchor
            self.stage.set_xy_position(pos)
            time.sleep(0.2)
            self.take_single()
        
        # Return to base
        self.stage.set_xy_position(anchor)

    def take_sequence_avg(self):
        """Take a grid photo and store it"""
        distance = 4
        positions = np.array([[1,0], [1,1], [0,1]])*distance
        anchor = np.array(self.stage.get_xy_position())

        self.take_single_avg()
            
        for i, position in enumerate(positions):
            pos = position + anchor
            self.stage.set_xy_position(pos)
            time.sleep(0.2)
            self.take_single()
        
        # Return to base
        self.stage.set_xy_position(anchor)

    
    
    def store_image(self, image: np.ndarray):
        self.photos.append(image)
        self.got_image.wakeAll()
    

    # =====================================================
    # ===============   Aquisitions   =====================
    # =====================================================
    
    def action(self, *actions):
        """Define action chains"""
        if len(actions) == 1:
            # Final action
            return actions[0]()
        else:
            return lambda: actions[0](*actions[1:])
    

    def start_aquisition(self, finish, *actions):
        actionsfunc = lambda: self.action(*actions)
        # Clear photo buffer
        self.photos = []
        self.aquisition_worker = AquisitionWorkerThread(self, actionsfunc)
        self.aquisition_worker.done.connect(finish)
        self.aquisition_worker.done.connect(self.finish_aquisition)

        self.aquiring_mutex.lock()
        self.aquiring = True
        self.aquiring_mutex.unlock()
        self.update_controls.emit()

        self.aquisition_worker.start()

    def finish_aquisition(self):
        self.aquiring_mutex.lock()
        self.aquiring = False
        self.aquiring_mutex.unlock()
        self.update_controls.emit()
    

    # =====================================================
    # =======   Complete measurement protocols   ==========
    # =====================================================

    # Snap and save one raw image
    def snap_photo(self):
        self.camera.new_frame.connect(self.save_image, Qt.ConnectionType.SingleShotConnection)
    

    def save_image(self, image: np.ndarray):
        dialog = QFileDialog(caption='Save Photo')
        dialog.setNameFilter('TIFF (*.tif)')
        dialog.setFileMode(QFileDialog.FileMode.AnyFile)
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        dialog.setDirectory(self.data_directory)

        if dialog.exec():
            filepath = dialog.selectedFiles()[0]
            filepath = os.path.splitext(filepath)[0]
            tiff.imwrite(filepath + '.tif', image)
        self.data_directory = dialog.directory()

    def snap_background(self):
        self.start_aquisition(self.set_background, self.take_sequence)
    
    def set_background(self):
        self.update_background.emit(pc.common_background(self.photos))
    
    # Background subtracted photos

    def snap_processed_photo(self):
        self.start_aquisition(self.save_processed_photo, self.take_sequence_avg)

    def save_processed_photo(self):
        dialog = QFileDialog(caption='Save Photo')
        dialog.setNameFilter('TIFF (*.tif)')
        dialog.setFileMode(QFileDialog.FileMode.AnyFile)
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        dialog.setDirectory(self.data_directory)
        if dialog.exec():
            filepath = dialog.selectedFiles()[0]
            filepath = os.path.splitext(filepath)[0]
            
            background = pc.common_background(self.photos[-4:])
            data = np.mean(self.photos[:-3], axis=0)
            diff = pc.background_subtracted(data, background)
            
            # also contains raw data
            tiff.imwrite(filepath + '.tif', pc.float_to_mono(diff))
            np.save(os.path.splitext(filepath)[0] + '.npy', self.photos)

            metadata = self.generate_metadata()
            with open(filepath+'.yaml', 'w') as file:
                yaml.dump(metadata, file)
        self.data_directory = dialog.directory()


    def laser_sweep(self):
        bandwidth = self.laser.bandwith
        band_radius = self.laser.bandwith/2
        dialog = SweepDialog(self, title='Laser Sweep Data', limits=(390+band_radius, 850-bandwidth, 390+bandwidth, 850-band_radius), defaults=(500, 600, 10), unit='nm')
        if dialog.exec() and not self.aquiring:
            self.wavelens = np.linspace(*dialog.get_values())
            self.start_aquisition(self.save_laser_data, self.take_laser_sweep, self.take_sequence_avg)
    
    def save_laser_data(self):
        dialog = QFileDialog(caption='Save Wavelength Sweep')
        dialog.setNameFilter('TIFF image sequence (*.tif)')
        dialog.setFileMode(QFileDialog.FileMode.AnyFile)
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        dialog.setDirectory(self.data_directory)
        if dialog.exec():
            filepath = dialog.selectedFiles()[0]
            filepath = os.path.splitext(filepath)[0]
            
            data = np.squeeze(self.photos)
            shape = np.shape(data)
            images = data.reshape(len(self.wavelens), self.shot_count+3, *shape[1:])
            np.save(filepath + '.npy', images)
            tiff.imwrite(filepath + '.tif', images[:,0])

            metadata = self.generate_metadata()
            metadata['Laser.wavelength [nm]'] = {
                'Start': int(self.wavelens[0]),
                'Stop': int(self.wavelens[-1]),
                'Number': len(self.wavelens)}
            with open(filepath+'.yaml', 'w') as file:
                yaml.dump(metadata, file)
        self.data_directory = dialog.directory()
    

    def z_sweep(self):
        dialog = SweepDialog(self, title='Z Sweep Data', limits=(-10, 10, -10, 10), defaults=(-1, 1, 10), unit='micron')
        if dialog.exec() and not self.aquiring:
            self.z_positions = np.linspace(*dialog.get_values())*10/1.4
            self.start_aquisition(self.save_z_data, self.take_z_sweep, self.take_sequence_avg)
    
    def save_z_data(self):
        dialog = QFileDialog(caption='Save Z Sweep')
        dialog.setNameFilter('TIFF image sequence (*.tif)')
        dialog.setFileMode(QFileDialog.FileMode.AnyFile)
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        dialog.setDirectory(self.data_directory)
        if dialog.exec():
            filepath = dialog.selectedFiles()[0]
            filepath = os.path.splitext(filepath)[0]

            data = np.squeeze(self.photos)
            shape = np.shape(data)
            images = data.reshape(len(self.z_positions), self.shot_count+3, *shape[1:])
            np.save(filepath + '.npy', images)
            tiff.imwrite(filepath + '.tif', images[:,0])

            metadata = self.generate_metadata()
            metadata['Setup.defocus [um]'] = {
                'Start': float(self.z_positions[0]),
                'Stop': float(self.z_positions[-1]),
                'Number': len(self.z_positions)}
            
            with open(filepath +'.yaml', 'w') as file:
                yaml.dump(metadata, file)
        self.data_directory = dialog.directory()
    

    def laser_defocus_sweep(self):
        self.wavelens = np.linspace(520, 522, 2)
        self.z_positions = np.linspace(-0.1, 0.1, 5)
        self.start_aquisition(self.save_laser_defocus_data,
                              self.take_z_sweep, self.take_laser_sweep, self.take_sequence_avg)
    
    def save_laser_defocus_data(self):
        dialog = QFileDialog(caption='Save Wavelength defocus Sweep')
        dialog.setNameFilter('raw data (*.npy)')
        dialog.setFileMode(QFileDialog.FileMode.AnyFile)
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        dialog.setDirectory(self.data_directory)
        if dialog.exec():
            filepath = dialog.selectedFiles()[0]
            filepath = os.path.splitext(filepath)[0]
            
            data = np.squeeze(self.photos)
            shape = np.shape(data)
            images = data.reshape(len(self.z_positions), len(self.wavelens), self.shot_count+3, *shape[1:])
            np.save(filepath + '.npy', images)

            metadata = self.generate_metadata()
            metadata['Laser.wavelength [nm]'] = {
                'Start': int(self.wavelens[0]),
                'Stop': int(self.wavelens[-1]),
                'Number': len(self.wavelens)}
            metadata['Setup.defocus [um]'] = {
                'Start': float(self.z_positions[0]),
                'Stop': float(self.z_positions[-1]),
                'Number': len(self.z_positions)}
            
            with open(filepath+'.yaml', 'w') as file:
                yaml.dump(metadata, file)
        self.data_directory = dialog.directory()
    
    # Media sweep
    def media_sweep(self):
        water = 10
        flowcell = 7
        waste = 1
        self.media = [water, 2, water, 3, water, 4, water, 5]
        self.start_aquisition(self.save_media_data, self.take_media_sweep, self.take_sequence_avg)
    
    def save_media_data(self):
        dialog = QFileDialog(caption='Save Media Data')
        dialog.setNameFilter('TIFF image sequence (*.tif)')
        dialog.setFileMode(QFileDialog.FileMode.AnyFile)
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        dialog.setDirectory(self.data_directory)
        if dialog.exec():
            filepath = dialog.selectedFiles()[0]
            filepath = os.path.splitext(filepath)[0]

            data = np.squeeze(self.photos)
            shape = np.shape(data)
            images = data.reshape(len(self.media), self.shot_count+3, *shape[1:])
            np.save(filepath + '.npy', images)
            tiff.imwrite(filepath + '.tif', images[:,0])

            metadata = self.generate_metadata()
            
            with open(filepath +'.yaml', 'w') as file:
                yaml.dump(metadata, file)
        self.data_directory = dialog.directory()

    

    ##

    def generate_metadata(self) -> dict:
        exposure_auto = self.camera.get_exposure_auto()
        if exposure_auto:
            exposure_time = 'auto'
        else:
            exposure_time = self.camera.get_exposure_time
        
        return({
            'Camera.fps': self.camera.get_fps(),
            'Camera.exposure_time [us]': exposure_time,
            'Camera.pixel_size [um]': self.pxsize,
            'Camera.averaging': self.shot_count,
            'Setup.magnification': self.magnification,
            'Laser.wavelength [nm]': self.laser.wavelen,
            'Laser.bandwith [nm]': self.laser.bandwith,
            'Laser.frequency [kHz]': self.laser.get_frequency()
        })
    
    # =====================================================
    # =================   Video   =========================
    # =====================================================
    
    def toggle_video(self, start: bool):
        if start:
            self.start_video()
        else:
            self.stop_video()

    def start_video(self):
        self.photos = []
        self.camera.new_frame.connect(self.write_frame)

    def write_frame(self, frame: np.ndarray):
        self.photos.append(frame)
    
    def stop_video(self):
        self.camera.new_frame.disconnect(self.write_frame)

        dialog = QFileDialog(caption='Save Video')
        dialog.setNameFilters(('Multi Page TIF (*.tif)', 'AVI Video (*.avi)'))
        dialog.setFileMode(QFileDialog.FileMode.AnyFile)
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        dialog.setDirectory(self.save_videos_directory)
        if dialog.exec():

            filepath = dialog.selectedFiles()[0]
            filepath = os.path.splitext(filepath)[0]
            nameFilter = dialog.selectedNameFilter()
            if '.tif' in nameFilter:
                photos = np.array(self.photos)
                if photos.dtype == np.uint16:
                    photos = (photos/256).astype(np.uint8)
                
                tiff.imwrite(filepath + '.tif', np.array(self.photos))

            elif '.avi' in nameFilter:
                fps = int(self.camera.get_fps())
                self.writer = cv2.VideoWriter(filepath + '.avi', cv2.VideoWriter_fourcc(*'XVID'), fps, (self.camera.roi_width, self.camera.roi_height), False)  # type: ignore

                for photo in self.photos:
                    # Image writer only support uint8
                    if photo.dtype == np.uint16:
                        self.writer.write((photo/256).astype(np.uint8))
                    elif (photo.dtype ==np.uint8):
                        self.writer.write(photo)

                
                self.writer.release()
        self.save_videos_directory = dialog.directory()
    
    def update_roi(self, roi):
        # Set ROI in camera
        self.camera.set_roi(roi)
        self.subtract_background = False
        self.background = None