from PySide6.QtCore import QStandardPaths, QCoreApplication, QDir, QTimer, QEvent, QFileInfo, Qt, Signal, QThread, QWaitCondition, QMutex, QSettings, QElapsedTimer
from PySide6.QtGui import QAction, QKeySequence, QCloseEvent, QIcon, QImage
from PySide6.QtWidgets import QMainWindow, QMessageBox, QLabel, QApplication, QFileDialog, QToolBar, QPushButton, QInputDialog

import os
import logging
import numpy as np



# Camera
import imagingcontrol4 as ic4

from widgets import VideoView, SweepDialog, PropertiesDialog, LaserWindow
from controllers.main_controller import MainController
import processing as pc


class PersistentWorkerThread(QThread):
    def __init__(self, func):
        super().__init__()
        self.func = func


class MainWindow(QMainWindow):
    new_processed_frame = Signal(np.ndarray)
    def __init__(self, controller: MainController):
        super().__init__(self)
        logging.basicConfig(level=logging.DEBUG)
        self.app_dir = QDir(os.path.dirname(os.path.abspath(__file__)))
        self.setWindowIcon(QIcon(self.app_dir.filePath("images/tis.ico")))

        # Setup storage
        self.appdata_directory = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
        picture_directory = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.PicturesLocation)
        video_directory = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.MoviesLocation)
        QDir(self.appdata_directory).mkpath('.')

        self.data_directory = picture_directory + '/Data'
        QDir(self.data_directory).mkpath('.')
        self.backgrounds_directory = picture_directory + '/Backgrounds'
        QDir(self.backgrounds_directory).mkpath('.')
        self.save_videos_directory = video_directory

        self.controller = controller


        # UI elements
        self.laser_window = LaserWindow(self)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.laser_window)
        self.laser_window.hide()

        self.video_view = VideoView(self)


        # Routes
        self.controller.update_controls.connect(self.update_controls)
        self.laser_window.centerChanged.connect(self.controller.laser.set_wavelen)
        self.laser_window.bandwidthChanged.connect(self.controller.laser.set_bandwith)

        self.temp_video_file = None

        self.controller.camera.new_frame.connect(self.update_display)
        self.controller.camera.state_changed.connect(self.update_controls)
        self.controller.camera.opened.connect(self.video_view.set_size)
        self.video_view.roi_set.connect(self.controller.camera.set_roi)
        
        
        self.move_stage_worker = PersistentWorkerThread(self.controller.stage.move_stage)
        self.video_view.move_stage.connect(self.move_stage_worker.func)

        self.background: np.ndarray | None = None
        self.subtract_background = False
        self.controller.update_background.connect(self.set_background)

        self.createUI()
        self.update_controls()
        self.controller.camera.reload_device()
            
            
    def createUI(self):
        self.resize(1024, 768)

        #=========#
        # Actions #
        #=========#
        application_path = os.path.abspath(os.path.dirname(__file__)) + os.sep


        self.acts = []
        def add_action(action):
            self.acts.append(action)
            return action
        
        self.device_select_act = add_action(QAction(QIcon(application_path + 'images/camera.png'), '&Select', self))
        self.device_select_act.setStatusTip('Select a video capture device')
        self.device_select_act.setShortcut(QKeySequence.StandardKey.Open)
        self.device_select_act.triggered.connect(self.controller.camera.onSelectDevice)

        self.device_properties_act = add_action(QAction(QIcon(application_path + 'images/imgset.png'), '&Camera Properties', self))
        self.device_properties_act.setStatusTip('Show device property dialog')
        self.device_properties_act.triggered.connect(self.controller.camera.onDeviceProperties)


        self.device_driver_properties_act = add_action(QAction('&Driver Properties', self))
        self.device_driver_properties_act.setStatusTip('Show device driver property dialog')
        self.device_driver_properties_act.triggered.connect(self.controller.camera.onDeviceDriverProperties)

        self.start_live_act = add_action(QAction(QIcon(application_path + 'images/livestream.png'), '&Live Stream', self))
        self.start_live_act.setStatusTip('Start and stop the live stream')
        self.start_live_act.setCheckable(True)
        self.start_live_act.triggered.connect(self.controller.camera.startStopStream)

        self.close_device_act = add_action(QAction('Close', self))
        self.close_device_act.setStatusTip('Close the currently opened device')
        self.close_device_act.setShortcuts(QKeySequence.StandardKey.Close)
        self.close_device_act.triggered.connect(self.controller.camera.onCloseDevice) 

        self.laser_parameters_act = add_action(QAction(QIcon(application_path + 'images/wavelen.png'), '&Laser Properties', self))
        self.laser_parameters_act.setStatusTip('Show laser properties dialog')
        self.laser_parameters_act.triggered.connect(lambda: self.laser_window.setVisible(not self.laser_window.isVisible()))

        self.set_roi_act = add_action(QAction('Select ROI', self))
        self.set_roi_act.setStatusTip('Draw a rectangle to set ROI')
        self.set_roi_act.setCheckable(True)
        self.set_roi_act.triggered.connect(lambda: self.toggle_mode('roi'))

        self.move_act = add_action(QAction('Move', self))
        self.move_act.setStatusTip('Move the sample by dragging the view')
        self.move_act.setCheckable(True)
        self.move_act.triggered.connect(lambda: self.toggle_mode('move'))

        self.subtract_background_act = add_action(QAction('Background Subtraction', self))
        self.subtract_background_act.setStatusTip('Toggle background subtraction')
        self.subtract_background_act.setCheckable(True)
        self.subtract_background_act.toggled.connect(self.set_background_subtraction)

        self.snap_background_act = add_action(QAction('&Snap Background', self))
        self.snap_background_act.setStatusTip('Snap background image')
        self.snap_background_act.triggered.connect(self.controller.snap_background)

        self.snap_raw_photo_act = add_action(QAction('Snap Raw Photo', self))
        self.snap_raw_photo_act.setStatusTip('Snap a single raw photo')
        self.snap_raw_photo_act.triggered.connect(self.controller.snap_photo)

        self.snap_processed_photo_act = add_action(QAction('Snap Photo'))
        self.snap_processed_photo_act.setStatusTip('Snap a single background subtracted photo')
        self.snap_processed_photo_act.triggered.connect(self.controller.snap_processed_photo)

        self.laser_sweep_act = add_action(QAction('Sweep Laser'))
        self.laser_sweep_act.triggered.connect(self.controller.laser_sweep)

        self.z_sweep_act = add_action(QAction('Defocus Sweep'))
        self.z_sweep_act.setStatusTip('Perform a focus sweep')
        self.z_sweep_act.triggered.connect(self.controller.z_sweep)

        self.z_wavelen_sweep_act = add_action(QAction('Defocus wavelen Sweep'))
        self.z_wavelen_sweep_act.setStatusTip('Perform a focus sweep')
        self.z_wavelen_sweep_act.triggered.connect(self.controller.laser_defocus_sweep)

        self.media_act = add_action(QAction('Vary Media'))
        self.media_act.setStatusTip('Perform a temporal variation of media')
        self.media_act.triggered.connect(self.controller.media_sweep)

        self.video_act = add_action(QAction(QIcon(application_path + 'images/recordstart.png'), '&Capture Video', self))
        self.video_act.setToolTip('Capture Video')
        self.video_act.setCheckable(True)
        self.video_act.toggled.connect(self.controller.toggle_video)

        self.grab_release_laser_act = add_action(QAction('Open Laser'))
        self.grab_release_laser_act.setCheckable(True)
        self.grab_release_laser_act.triggered.connect(self.controller.laser.toggle_laser)

        self.grab_release_pump_act = add_action(QAction('Open Pump'))
        self.grab_release_pump_act.setCheckable(True)
        self.grab_release_pump_act.triggered.connect(self.controller.pump.toggle)

        self.change_setup_act = add_action(QAction('Setup Properties'))
        self.change_setup_act.triggered.connect(self.controller.set_setup_parameters)

        self.cancel_aquisition_act = add_action(QAction('Cancel aquisition'))
        self.cancel_aquisition_act.triggered.connect(self.controller.finish_aquisition)

        self.clean_pump_act = add_action(QAction('Clean pump'))
        self.clean_pump_act.triggered.connect(self.controller.pump.clean_pump)



        exit_act = add_action(QAction('E&xit', self))
        exit_act.setShortcut(QKeySequence.StandardKey.Quit)
        exit_act.setStatusTip('Exit program')
        exit_act.triggered.connect(self.close)

        #=========#
        # Menubar #
        #=========#

        file_menu = self.menuBar().addMenu('&File')
        file_menu.addAction(exit_act)

        device_menu = self.menuBar().addMenu('&Device')
        device_menu.addAction(self.device_select_act)
        device_menu.addAction(self.device_properties_act)
        device_menu.addAction(self.laser_parameters_act)
        device_menu.addAction(self.device_driver_properties_act)
        device_menu.addAction(self.set_roi_act)
        device_menu.addAction(self.move_act)
        device_menu.addAction(self.start_live_act)
        device_menu.addSeparator()
        device_menu.addAction(self.grab_release_laser_act)
        device_menu.addAction(self.grab_release_pump_act)
        device_menu.addAction(self.close_device_act)
        device_menu.addAction(self.change_setup_act)
        device_menu.addAction(self.clean_pump_act)

        view_menu = self.menuBar().addMenu('&View')
        view_menu.addAction(self.snap_background_act)
        view_menu.addAction(self.subtract_background_act)

        capture_menu = self.menuBar().addMenu('&Capture')
        capture_menu.addAction(self.snap_raw_photo_act)
        capture_menu.addAction(self.snap_processed_photo_act)
        capture_menu.addSeparator()
        capture_menu.addAction(self.z_sweep_act)
        capture_menu.addAction(self.z_wavelen_sweep_act)
        capture_menu.addAction(self.media_act)
        capture_menu.addAction(self.cancel_aquisition_act)
        



        #=========#
        # Toolbar #
        #=========#

        toolbar = QToolBar(self)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar)
        toolbar.addAction(self.device_select_act)
        toolbar.addAction(self.device_properties_act)
        toolbar.addAction(self.laser_parameters_act)
        #toolbar.addAction(self.trigger_mode_act)
        toolbar.addSeparator()
        toolbar.addAction(self.start_live_act)
        toolbar.addAction(self.video_act)
        toolbar.addSeparator()
        toolbar.addAction(self.set_roi_act)
        toolbar.addAction(self.move_act)
        toolbar.addSeparator()
        toolbar.addAction(self.snap_raw_photo_act)
        toolbar.addAction(self.snap_processed_photo_act)
        toolbar.addSeparator()
        toolbar.addAction(self.laser_sweep_act)
        toolbar.addAction(self.z_sweep_act)
        toolbar.addAction(self.media_act)

        
        # button = QPushButton('Test', toolbar)
        # button.clicked.connect(self.test)
        # toolbar.addWidget(button)



        self.setCentralWidget(self.video_view)
        

        self.statusBar().showMessage('Ready')
        self.aquisition_label = QLabel('', self.statusBar())
        self.statusBar().addPermanentWidget(self.aquisition_label)
        self.statistics_label = QLabel('', self.statusBar())
        self.controller.camera.statistics_update.connect(lambda s1, s2: (self.statistics_label.setText(s1), self.statistics_label.setToolTip(s2)))
        self.statusBar().addPermanentWidget(self.statistics_label)
        self.statusBar().addPermanentWidget(QLabel('  '))
        self.camera_label = QLabel(self.statusBar())
        self.statusBar().addPermanentWidget(self.camera_label)
        self.controller.camera.label_update.connect(self.camera_label.setText)
    
    # def test(self, button):
    #         print(self.laser.open)

    

    def update_laser_control(self):
        if self.controller.laser.open:
            bandwidth = self.controller.laser.bandwith
            wavelen = self.controller.laser.wavelen
            self.laser_window.set_values(wavelen, bandwidth)
        

    def update_controls(self):
        # Depending booleans
        aquiring = self.controller.aquiring
        pump_open = self.controller.pump.open
        laser_open = self.controller.laser.open
        streaming = self.controller.camera.grabber.is_streaming
        valid_camera  = self.controller.camera.grabber.is_device_valid
        camera_open = self.controller.camera.grabber.is_device_open

        self.laser_window.setVisible(self.controller.laser.open)
        self.laser_parameters_act.setEnabled(self.controller.laser.open)

        if not camera_open:
            self.statistics_label.clear()
        
        xy_stage_connected = not not self.controller.stage.xy_stage
        z_stage_connected = not not self.controller.stage.z_stage


        # Non-aquisition
        if not aquiring:
            for act in self.acts:
                act.setEnabled(True)

        
        # Devices
        self.grab_release_laser_act.setChecked(laser_open)
        self.laser_parameters_act.setEnabled(laser_open)

        self.grab_release_pump_act.setChecked(pump_open)

        self.device_properties_act.setEnabled(valid_camera)
        self.device_driver_properties_act.setEnabled(valid_camera)
        self.start_live_act.setEnabled(valid_camera)
        self.start_live_act.setChecked(streaming)
        self.video_act.setEnabled(streaming)
        self.close_device_act.setEnabled(camera_open)

        # Captures
        self.snap_background_act.setEnabled(streaming and xy_stage_connected)
        self.snap_processed_photo_act.setEnabled(streaming and xy_stage_connected)
        self.snap_raw_photo_act.setEnabled(streaming)

        self.laser_sweep_act.setEnabled(streaming and laser_open)
        self.media_act.setEnabled(streaming and pump_open)
        self.z_sweep_act.setEnabled(streaming and z_stage_connected and xy_stage_connected)
        self.z_wavelen_sweep_act.setEnabled(streaming and z_stage_connected and xy_stage_connected and laser_open)

        # Video view functions
        self.set_roi_act.setEnabled(valid_camera and not self.video_view.background.rect().isEmpty())
        self.move_act.setEnabled(streaming and xy_stage_connected)
        self.move_act.setChecked(self.video_view.mode == 'move')
        self.set_roi_act.setChecked(self.video_view.mode == 'roi')

        self.subtract_background_act.setEnabled(self.background is not None)
        self.subtract_background_act.setChecked(self.subtract_background)
        
        # Aquisition
        if aquiring:
            self.video_view.mode = 'navigation'
            self.subtract_background = False
            self.subtract_background_act.setChecked(False)
            
            for act in self.acts:
                act.setEnabled(False)
        
        self.cancel_aquisition_act.setEnabled(aquiring)
    
    

    def set_background_subtraction(self, value: bool):
        self.subtract_background = value
    
    def set_background(self, background):
        self.background = background
    
    def toggle_mode(self, mode):
        if self.video_view.mode == mode:
            self.video_view.mode = 'navigation'
        else:
            self.video_view.mode = mode
            
        self.update_controls()
        
    
    def update_display(self, frame: np.ndarray):
        if (self.subtract_background and self.background is not None):
            # (reference + signal) / reference
            diff = pc.background_subtracted(frame, self.background)
            frame = pc.float_to_mono(diff)
        self.new_processed_frame.emit(frame)
        self.video_view.update_image(frame)