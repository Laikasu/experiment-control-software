
from threading import Lock

from PySide6.QtCore import QStandardPaths, QDir, QTimer, QEvent, QFileInfo, Qt, Signal, QThread
from PySide6.QtGui import QAction, QKeySequence, QCloseEvent, QIcon, QImage
from PySide6.QtWidgets import QMainWindow, QMessageBox, QLabel, QApplication, QFileDialog, QToolBar

import os
from datetime import datetime
import numpy as np
import time
import cv2

from pymmcore_plus import CMMCorePlus

import imagingcontrol4 as ic4
from videoview import VideoView

from processing import *


got_processed_photo_EVENT = QEvent.Type(QEvent.Type.User + 1)
DEVICE_LOST_EVENT = QEvent.Type(QEvent.Type.User + 2)

class GotPhotoEvent(QEvent):
    def __init__(self, buffer: ic4.ImageBuffer):
        QEvent.__init__(self, got_processed_photo_EVENT)
        self.image_buffer = buffer

class AquisitionThread(QThread):
    finished = Signal()
    def __init__(self, mmc, aquisitionfunc):
        super().__init__()
        self.mmc = mmc
        self.func = aquisitionfunc
    def run(self):
        self.func()
        self.finished.emit()
        

class MainWindow(QMainWindow):
    new_frame = Signal(np.ndarray)
    def __init__(self):
        application_path = os.path.abspath(os.path.dirname(__file__)) + os.sep
        QMainWindow.__init__(self)
        self.setWindowIcon(QIcon(application_path + "/images/tis.ico"))

        # Setup stage
        # Setup microscope connection

        mm_dir = "C:/Program Files/Micro-Manager-2.0"
        self.mmc = CMMCorePlus.instance()
        self.mmc.setDeviceAdapterSearchPaths([mm_dir])
        self.xy_position = 0
        #self.mmc.loadSystemConfiguration()
        #self.mmc.loadSystemConfiguration(os.path.join(application_path, "MMConfig.cfg"))
        self.z_stage = self.mmc.getFocusDevice()
        self.xy_stage = self.mmc.getXYStageDevice()
        if not self.z_stage:
            print("z_stage not found")
        if not self.xy_stage:
            print("xy_stage not found")

        

        # Make sure the %appdata%/demoapp directory exists
        appdata_directory = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
        picture_directory = QStandardPaths.writableLocation(QStandardPaths.PicturesLocation)
        video_directory = QStandardPaths.writableLocation(QStandardPaths.MoviesLocation)
        QDir(appdata_directory).mkpath(".")
        

        self.data_directory = picture_directory + "/Data"
        QDir(self.data_directory).mkpath(".")
        self.backgrounds_directory = picture_directory + "/Backgrounds"
        QDir(self.backgrounds_directory).mkpath(".")
        self.save_videos_directory = video_directory

        self.device_file = appdata_directory + "/device.json"

        self.shoot_photo_mutex = Lock()
        self.shoot_photo = False
        self.got_image = self.got_raw_photo

        self.aquiring = False
        self.aquiring_mutex = Lock()

        self.grabber = ic4.Grabber()
        self.grabber.event_add_device_lost(lambda g: QApplication.postEvent(self, QEvent(DEVICE_LOST_EVENT)))

        self.video_view = VideoView(self)
        self.video_view.roi_set.connect(self.update_roi)
        self.new_frame.connect(self.update_pixmap)

        self.background: np.ndarray = None
        self.subtract_background = False

        class Listener(ic4.QueueSinkListener):
            def sink_connected(self, sink: ic4.QueueSink, image_type: ic4.ImageType, min_buffers_required: int) -> bool:
                # Allocate more buffers than suggested, because we temporarily take some buffers
                # out of circulation when saving an image or video files.
                sink.alloc_and_queue_buffers(min_buffers_required + 2)
                return True

            def sink_disconnected(self, sink: ic4.QueueSink):
                pass

            def frames_queued(listener, sink: ic4.QueueSink):
                buf = sink.pop_output_buffer()

                with self.shoot_photo_mutex:
                    if self.shoot_photo:
                        self.shoot_photo = False

                        # Send an event to the main thread with a reference to 
                        # the main thread of our GUI. 
                        QApplication.postEvent(self, GotPhotoEvent(buf))
                
                buffer = buf.numpy_copy()

                # Visible area
                bounds = self.video_view.get_bounds()
                region = np.index_exp[bounds[1]:bounds[3], bounds[0]:bounds[2]]
                
                if (self.subtract_background):
                    if (self.background is not None):
                        # (reference + signal) / reference
                        diff = background_subtracted(buffer[region], self.background[region])
                        buffer = float_to_mono(diff)
                        
                
                self.new_frame.emit(buffer)
                # Connect the buffer's chunk data to the device's property map
                # This allows for properties backed by chunk data to be updated
                self.device_property_map.connect_chunkdata(buf)
                #self.update_frame(buffer)

        

        self.sink = ic4.QueueSink(Listener())

        self.property_dialog = None

        self.createUI()

        if QFileInfo.exists(self.device_file):
            try:
                self.grabber.device_open_from_state_file(self.device_file)
                self.onDeviceOpened()
            except ic4.IC4Exception as e:
                QMessageBox.information(self, "", f"Loading last used device failed: {e}", QMessageBox.StandardButton.Ok)
        
        
        self.updateControls()
    
    

    def createUI(self):
        self.resize(1024, 768)

        #=========#
        # Actions #
        #=========#
        application_path = os.path.abspath(os.path.dirname(__file__)) + os.sep
        
        self.device_select_act = QAction(QIcon(application_path + "images/camera.png"), "&Select", self)
        self.device_select_act.setStatusTip("Select a video capture device")
        self.device_select_act.setShortcut(QKeySequence.Open)
        self.device_select_act.triggered.connect(self.onSelectDevice)

        self.device_properties_act = QAction(QIcon(application_path + "images/imgset.png"), "&Properties", self)
        self.device_properties_act.setStatusTip("Show device property dialog")
        self.device_properties_act.triggered.connect(self.onDeviceProperties)

        self.device_driver_properties_act = QAction("&Driver Properties", self)
        self.device_driver_properties_act.setStatusTip("Show device driver property dialog")
        self.device_driver_properties_act.triggered.connect(self.onDeviceDriverProperties)

        self.trigger_mode_act = QAction(QIcon(application_path + "images/triggermode.png"), "&Trigger Mode", self)
        self.trigger_mode_act.setStatusTip("Enable and disable trigger mode")
        self.trigger_mode_act.setCheckable(True)
        self.trigger_mode_act.triggered.connect(self.onToggleTriggerMode)

        self.start_live_act = QAction(QIcon(application_path + "images/livestream.png"), "&Live Stream", self)
        self.start_live_act.setStatusTip("Start and stop the live stream")
        self.start_live_act.setCheckable(True)
        self.start_live_act.triggered.connect(self.startStopStream)

        self.close_device_act = QAction("Close", self)
        self.close_device_act.setStatusTip("Close the currently opened device")
        self.close_device_act.setShortcuts(QKeySequence.Close)
        self.close_device_act.triggered.connect(self.onCloseDevice)

        self.set_roi_act = QAction("Select ROI", self)
        self.set_roi_act.setStatusTip("Draw a rectangle to set ROI")
        self.set_roi_act.setCheckable(True)
        self.set_roi_act.triggered.connect(self.video_view.toggle_roi_mode)

        self.subtract_background_act = QAction("Background Subtraction", self)
        self.subtract_background_act.setStatusTip("Toggle background subtraction")
        self.subtract_background_act.setCheckable(True)
        self.subtract_background_act.triggered.connect(self.toggle_background_subtraction)

        self.snap_background_act = QAction("&Snap Background", self)
        self.snap_background_act.setStatusTip("Snap background image")
        self.snap_background_act.triggered.connect(self.snap_background)

        self.snap_raw_photo_act = QAction("Snap Raw Photo", self)
        self.snap_raw_photo_act.setStatusTip("Snap a single raw photo")
        self.snap_raw_photo_act.triggered.connect(self.snap_raw_photo)

        self.snap_processed_photo_act = QAction("Snap Photo")
        self.snap_processed_photo_act.setStatusTip("Snap a single background subtracted photo")
        self.snap_processed_photo_act.triggered.connect(self.snap_processed_photo)

        self.z_sweep_act = QAction("Focus Sweep")
        self.z_sweep_act.setStatusTip("Perform a focus sweep")
        self.z_sweep_act.triggered.connect(self.z_sweep)


        exit_act = QAction("E&xit", self)
        exit_act.setShortcut(QKeySequence.Quit)
        exit_act.setStatusTip("Exit program")
        exit_act.triggered.connect(self.close)

        #=========#
        # Menubar #
        #=========#

        file_menu = self.menuBar().addMenu("&File")
        file_menu.addAction(exit_act)

        device_menu = self.menuBar().addMenu("&Device")
        device_menu.addAction(self.device_select_act)
        device_menu.addAction(self.device_properties_act)
        device_menu.addAction(self.device_driver_properties_act)
        device_menu.addAction(self.set_roi_act)
        device_menu.addAction(self.trigger_mode_act)
        device_menu.addAction(self.start_live_act)
        device_menu.addSeparator()
        device_menu.addAction(self.close_device_act)

        capture_menu = self.menuBar().addMenu("&Capture")
        capture_menu.addAction(self.snap_raw_photo_act)
        capture_menu.addAction(self.snap_processed_photo_act)
        capture_menu.addAction(self.z_sweep_act)
        capture_menu.addAction(self.snap_background_act)
        capture_menu.addAction(self.subtract_background_act)
        



        #=========#
        # Toolbar #
        #=========#

        toolbar = QToolBar(self)
        self.addToolBar(Qt.TopToolBarArea, toolbar)
        toolbar.addAction(self.device_select_act)
        toolbar.addAction(self.device_properties_act)
        toolbar.addSeparator()
        toolbar.addAction(self.trigger_mode_act)
        toolbar.addSeparator()
        toolbar.addAction(self.start_live_act)
        toolbar.addSeparator()
        toolbar.addAction(self.subtract_background_act)
        toolbar.addAction(self.set_roi_act)
        toolbar.addSeparator()
        toolbar.addAction(self.snap_background_act)
        toolbar.addAction(self.snap_raw_photo_act)
        toolbar.addAction(self.snap_processed_photo_act)
        toolbar.addAction(self.z_sweep_act)



        self.setCentralWidget(self.video_view)
        

        self.statusBar().showMessage("Ready")
        self.aquisition_label = QLabel("", self.statusBar())
        self.statusBar().addPermanentWidget(self.aquisition_label)
        self.statistics_label = QLabel("", self.statusBar())
        self.statusBar().addPermanentWidget(self.statistics_label)
        self.statusBar().addPermanentWidget(QLabel("  "))
        self.camera_label = QLabel(self.statusBar())
        self.statusBar().addPermanentWidget(self.camera_label)

        self.update_statistics_timer = QTimer()
        self.update_statistics_timer.timeout.connect(self.onUpdateStatisticsTimer)
        self.update_statistics_timer.start()
        

    def onCloseDevice(self):
        if self.grabber.is_streaming:
            self.startStopStream()
        
        try:
            self.grabber.device_close()
        except:
            pass

        self.device_property_map = None
        self.display.display_buffer(None)

        self.updateControls()

    def closeEvent(self, ev: QCloseEvent):
        if self.grabber.is_streaming:
            self.grabber.stream_stop()

        if self.grabber.is_device_valid:
            self.grabber.device_save_state_to_file(self.device_file)
    
    def customEvent(self, ev: QEvent):
        if ev.type() == DEVICE_LOST_EVENT:
            self.onDeviceLost()
        elif ev.type() == got_processed_photo_EVENT:
            self.got_image(ev.image_buffer)
            

    def onSelectDevice(self):
        dlg = ic4.pyside6.DeviceSelectionDialog(self.grabber, parent=self)
        if dlg.exec() == 1:
            if not self.property_dialog is None:
                self.property_dialog.update_grabber(self.grabber)
            
            self.onDeviceOpened()
        self.updateControls()

    def onDeviceProperties(self):
        if self.property_dialog is None:
            self.property_dialog = ic4.pyside6.PropertyDialog(self.grabber, parent=self, title="Device Properties")
            # set default vis
        
        self.property_dialog.show()

    def onDeviceDriverProperties(self):
        dlg = ic4.pyside6.PropertyDialog(self.grabber.driver_property_map, parent=self, title="Device Driver Properties")
        # set default vis

        dlg.exec()

        self.updateControls()

    def onToggleTriggerMode(self):
        try:
            self.device_property_map.set_value(ic4.PropId.TRIGGER_MODE, self.trigger_mode_act.isChecked())
        except ic4.IC4Exception as e:
            QMessageBox.critical(self, "", f"{e}", QMessageBox.StandardButton.Ok)
    
    def onShootBG(self):
        with self.shoot_photo_mutex:
            self.shoot_photo = True
            self.shoot_bg = True

    def onUpdateStatisticsTimer(self):
        if not self.grabber.is_device_valid:
            return
        
        try:
            stats = self.grabber.stream_statistics
            text = f"Frames Delivered: {stats.sink_delivered} Dropped: {stats.device_transmission_error}/{stats.device_underrun}/{stats.transform_underrun}/{stats.sink_underrun}"
            self.statistics_label.setText(text)
            tooltip = (
                f"Frames Delivered: {stats.sink_delivered}"
                f"Frames Dropped:"
                f"  Device Transmission Error: {stats.device_transmission_error}"
                f"  Device Underrun: {stats.device_underrun}"
                f"  Transform Underrun: {stats.transform_underrun}"
                f"  Sink Underrun: {stats.sink_underrun}"
            )
            self.statistics_label.setToolTip(tooltip)
        except ic4.IC4Exception:
            pass

    def onDeviceLost(self):
        QMessageBox.warning(self, "", f"The video capture device is lost!", QMessageBox.StandardButton.Ok)

        # stop video

        self.updateCameraLabel()
        self.updateControls()

    def onDeviceOpened(self):
        self.device_property_map = self.grabber.device_property_map

        self.device_property_map.set_value(ic4.PropId.OFFSET_AUTO_CENTER, "Off")
        self.width = self.device_property_map.get_value_int(ic4.PropId.WIDTH)
        self.height = self.device_property_map.get_value_int(ic4.PropId.HEIGHT)
        self.video_view.set_size(
            self.device_property_map.get_value_int(ic4.PropId.WIDTH_MAX),
            self.device_property_map.get_value_int(ic4.PropId.HEIGHT_MAX),
            self.device_property_map.get_value_int(ic4.PropId.OFFSET_X),
            self.device_property_map.get_value_int(ic4.PropId.OFFSET_Y))

        trigger_mode = self.device_property_map.find(ic4.PropId.TRIGGER_MODE)
        trigger_mode.event_add_notification(self.updateTriggerControl)

        self.updateCameraLabel()

        # if start_stream_on_open
        self.startStopStream()

    def updateTriggerControl(self, p: ic4.Property):
        if not self.grabber.is_device_valid:
            self.trigger_mode_act.setChecked(False)
            self.trigger_mode_act.setEnabled(False)
        else:
            try:
                self.trigger_mode_act.setChecked(self.device_property_map.get_value_str(ic4.PropId.TRIGGER_MODE) == "On")
                self.trigger_mode_act.setEnabled(True)
            except ic4.IC4Exception:
                self.trigger_mode_act.setChecked(False)
                self.trigger_mode_act.setEnabled(False)

    def updateControls(self):
        if not self.grabber.is_device_open:
            self.statistics_label.clear()
        
        self.device_properties_act.setEnabled(self.grabber.is_device_valid and not self.aquiring)
        self.device_driver_properties_act.setEnabled(self.grabber.is_device_valid and not self.aquiring)
        self.start_live_act.setEnabled(self.grabber.is_device_valid and not self.aquiring)
        self.start_live_act.setChecked(self.grabber.is_streaming)
        self.close_device_act.setEnabled(self.grabber.is_device_open and not self.aquiring)
        self.snap_background_act.setEnabled(self.grabber.is_streaming and not self.aquiring and self.xy_stage)
        self.snap_processed_photo_act.setEnabled(self.grabber.is_streaming and not self.aquiring and self.xy_stage)
        self.snap_raw_photo_act.setEnabled(self.grabber.is_streaming and not self.aquiring)
        self.z_sweep_act.setEnabled(self.grabber.is_streaming and not self.aquiring and self.z_stage and self.xy_stage)
        self.set_roi_act.setEnabled(self.grabber.is_device_valid and not self.aquiring)
        self.subtract_background_act.setEnabled(self.background is not None)

        self.updateTriggerControl(None)

    def updateCameraLabel(self):
        try:
            info = self.grabber.device_info
            self.camera_label.setText(f"{info.model_name} {info.serial}")
        except ic4.IC4Exception:
            self.camera_label.setText("No Device")


    def startStopStream(self):
        try:
            if self.grabber.is_device_valid:
                if self.grabber.is_streaming:
                    self.grabber.stream_stop()
                else:
                    self.grabber.stream_setup(self.sink)

        except ic4.IC4Exception as e:
            QMessageBox.critical(self, "", f"{e}", QMessageBox.StandardButton.Ok)

        self.updateControls()
    

    # Functions to take raw images and aquisitions
    
    # Snap and save raw image
    def snap_raw_photo(self):
        self.got_image = self.got_raw_photo
        with self.shoot_photo_mutex:
            self.shoot_photo = True
    
    def got_raw_photo(self, image_buffer: ic4.ImageBuffer):        
        dialog = QFileDialog(self, "Save Photo")
        dialog.setNameFilter("TIFF (*.tif)")
        dialog.setFileMode(QFileDialog.FileMode.AnyFile)
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        dialog.setDirectory(self.data_directory)

        if dialog.exec():
            full_path = dialog.selectedFiles()[0]
            self.data_directory = QFileInfo(full_path).absolutePath()

            try:
                image_buffer.save_as_tiff(full_path)
                
            except ic4.IC4Exception as e:
                QMessageBox.critical(self, "", f"{e}", QMessageBox.StandardButton.Ok)

    # Snap a sequence of images in a grid to calculate the background and save it.
    def snap_background(self):
        self.photos = np.zeros((4, self.height, self.width, 1), dtype=np.uint16)
        self.got_image = self.got_background
        with self.aquiring_mutex:
            if not self.aquiring:
                self.aquiring = True
                self.aquisition_worker = AquisitionThread(self.mmc, self.take_sequence)
                self.aquisition_worker.finished.connect(self.update_background)
                self.aquisition_worker.finished.connect(self.finish_aquisition)
                self.aquisition_worker.start()
        self.updateControls()
    

    def got_background(self, image_buffer: ic4.ImageBuffer):
        self.photos[self.xy_position] = image_buffer.numpy_wrap()


    def update_background(self):
        self.background = common_background(self.photos)
        self.updateControls()

    def snap_processed_photo(self):
        self.photos = np.zeros((4, self.height, self.width, 1))
        self.got_image = self.got_processed_photo
        with self.aquiring_mutex:
            if not self.aquiring:
                self.aquiring = True
                self.aquisition_worker = AquisitionThread(self.mmc, self.take_sequence)
                self.aquisition_worker.finished.connect(self.save_processed_photo)
                self.aquisition_worker.finished.connect(self.finish_aquisition)
                self.aquisition_worker.start()
        self.updateControls()

    def got_processed_photo(self, image_buffer: ic4.ImageBuffer):
        self.photos[self.xy_position] = image_buffer.numpy_wrap()
    
    def save_processed_photo(self):
        dialog = QFileDialog(self, "Save Photo")
        dialog.setNameFilter("TIFF (*.tif)")
        dialog.setFileMode(QFileDialog.FileMode.AnyFile)
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        dialog.setDirectory(self.data_directory)

        if dialog.exec():
            full_path = dialog.selectedFiles()[0]
            self.data_directory = QFileInfo(full_path).absolutePath()

            try:
                background = common_background(self.photos)
                data = self.photos[0]
                diff = background_subtracted(data, background)
                # also contains raw data
                cv2.imwrite(full_path, float_to_mono(diff))
                np.save(os.path.splitext(full_path)[0] + ".npy", self.photos)
                
            except ic4.IC4Exception as e:
                QMessageBox.critical(self, "", f"{e}", QMessageBox.StandardButton.Ok)

    
    def z_sweep(self):
        self.got_image = self.got_sweep_photo
        with self.aquiring_mutex:
            if not self.aquiring:
                self.aquiring = True
                self.aquisition_worker = AquisitionThread(self.mmc, self.take_z_sweep)
                self.aquisition_worker.finished.connect(self.finish_aquisition)
                self.aquisition_worker.start()
        self.updateControls()
    
    def got_sweep_photo(self, image_buffer: ic4.ImageBuffer):
        self.photos[self.xy_position] = image_buffer.numpy_wrap()

    def save_z_photos(self):
        np.save(os.join(self.data_directory, f"zsweep_{self.z_position}"), self.photos)


    def toggle_background_subtraction(self):
        self.subtract_background = not self.subtract_background
    
    def take_z_sweep(self):
        z_zero = np.array(self.mmc.getZPosition(self.z_stage))
        N = 20
        z_positions = np.linspace(-5, 5, N)
        for i, z in enumerate(z_positions):
            self.aquisition_label.setText(f"Aquiring Data: z sweep progression {i+1}/{N}")
            self.photos = np.zeros((4, self.height, self.width))
            pos = z_zero + z
            self.z_position = i
            self.mmc.setZPosition(pos)
            self.mmc.waitForDevice(self.z_stage)
            self.take_sequence()
            self.save_z_photos()
        self.mmc.setZPosition(z_zero)
        self.aquisition_label.setText("Calculating Images")
        self.startStopStream()
        self.save_z_sweep(N)
        self.startStopStream()

    
    def save_z_sweep(self, length):
        for i in range(length):
            name = os.join(self.data_directory, f"zsweep_{i}")
            photos = np.load(name + ".npy")
            background = common_background(photos)
            data = photos[0]
            diff = np.divide(np.subtract(self.photos[0], data, dtype=np.int32), background)
            # also contains raw data
            cv2.imwrite(name + ".tif", float_to_mono(diff))
        self.aquisition_label.setText("")
        self.statusBar().showMessage("Done!")
    

        


    def take_sequence(self):
        distance = 10
        positions = np.array([[0,0], [1,0], [1,1], [0,1]])*distance
        anchor = np.array(self.mmc.getXYPosition(self.xy_stage))
        for i, position in enumerate(positions):
            pos = position + anchor
            self.xy_position = i
            self.mmc.setXYPosition(pos[0], pos[1])
            self.mmc.waitForDevice(self.xy_stage)
            # shoot photo and wait for it to be shot
            with self.shoot_photo_mutex:
                self.shoot_photo = True
            
            while self.shoot_photo:
                pass
        
        # Return to base
        self.mmc.setXYPosition(anchor[0], anchor[1])

    def finish_aquisition(self):
        self.aquiring = False
        self.updateControls()

    def update_roi(self, roi):
        # Go out of roi mode in UI
        self.set_roi_act.setChecked(False)

        # Set ROI in camera
        self.startStopStream()
        self.device_property_map.set_value(ic4.PropId.WIDTH, int(roi.width()))
        self.device_property_map.set_value(ic4.PropId.HEIGHT, int(roi.height()))
        self.device_property_map.set_value(ic4.PropId.OFFSET_X, int(roi.left()))
        self.device_property_map.set_value(ic4.PropId.OFFSET_Y, int(roi.top()))
        self.startStopStream()
        self.width = roi.width()
        self.height = roi.height()
    
    def update_pixmap(self, frame):
        self.video_view.update_image(frame)