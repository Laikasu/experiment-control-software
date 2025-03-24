import imagingcontrol4 as ic4

from PySide6.QtCore import QStandardPaths, QDir, QTimer, QEvent, QFileInfo, Qt, Signal, QThread, QObject
from PySide6.QtGui import QAction, QKeySequence, QCloseEvent, QIcon, QImage
from PySide6.QtWidgets import QMainWindow, QMessageBox, QLabel, QApplication, QFileDialog, QToolBar

import numpy as np

DEVICE_LOST_EVENT = QEvent.Type(QEvent.Type.User + 1)
    

class Camera(QObject):
    new_frame = Signal(np.ndarray)
    state_changed = Signal()
    camera_opened = Signal(int, int, int, int)

    def __init__(self, parent):
        super().__init__(parent)
        self.grabber = ic4.Grabber()
        self.grabber.event_add_device_lost(lambda g: QApplication.postEvent(self, QEvent(DEVICE_LOST_EVENT)))
        self.device_property_map = None
        self.property_dialog = None
        
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
                
                self.new_frame.emit(buf.numpy_copy())
                # Connect the buffer's chunk data to the device's property map
                # This allows for properties backed by chunk data to be updated
                self.device_property_map.connect_chunkdata(buf)
                #self.update_frame(buffer)
        self.sink = ic4.QueueSink(Listener())


        appdata_directory = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
        self.device_file = appdata_directory + '/device.json'
        if QFileInfo.exists(self.device_file):
            try:
                self.grabber.device_open_from_state_file(self.device_file)
                self.onDeviceOpened()
            except ic4.IC4Exception as e:

                QMessageBox.information(self, '', f'Loading last used device failed: {e}', QMessageBox.StandardButton.Ok)
    

    def closeEvent(self, ev: QCloseEvent):
        if self.grabber.is_device_valid:
            self.grabber.device_save_state_to_file(self.device_file)
        if self.grabber.is_streaming:
            self.grabber.stream_stop()
        
        del(self.grabber)
        del(self.sink)
        #del(self.device_property_map)
    

    def onCloseDevice(self):
        if self.grabber.is_streaming:
            self.startStopStream()
        
        try:
            self.grabber.device_close()
        except:
            pass

        self.device_property_map = None

    
    def onSelectDevice(self, parent):
        dlg = ic4.pyside6.DeviceSelectionDialog(self.grabber, parent=parent)
        if dlg.exec() == 1:
            if not self.property_dialog is None:
                self.property_dialog.update_grabber(self.grabber)
            
            self.onDeviceOpened()
    
    def onDeviceProperties(self, parent):
        if self.property_dialog is None:
            self.property_dialog = ic4.pyside6.PropertyDialog(self.grabber, parent=parent, title='Device Properties')
            # set default vis
        
        self.property_dialog.show()
    
    def onDeviceDriverProperties(self, parent):
        dlg = ic4.pyside6.PropertyDialog(self.grabber.driver_property_map, parent=parent, title='Device Driver Properties')
        # set default vis

        dlg.exec()
    
    def onUpdateStatisticsTimer(self, statistics_label):
        if not self.grabber.is_device_valid:
            return
        
        try:
            stats = self.grabber.stream_statistics
            text = f'Frames Delivered: {stats.sink_delivered} Dropped: {stats.device_transmission_error}/{stats.device_underrun}/{stats.transform_underrun}/{stats.sink_underrun}'
            statistics_label.setText(text)
            tooltip = (
                f'Frames Delivered: {stats.sink_delivered}'
                f'Frames Dropped:'
                f'  Device Transmission Error: {stats.device_transmission_error}'
                f'  Device Underrun: {stats.device_underrun}'
                f'  Transform Underrun: {stats.transform_underrun}'
                f'  Sink Underrun: {stats.sink_underrun}'
            )
            statistics_label.setToolTip(tooltip)
        except ic4.IC4Exception:
            pass
    
    def onDeviceLost(self):
        QMessageBox.warning(self, '', f'The video capture device is lost!', QMessageBox.StandardButton.Ok)

        # stop video

        self.updateCameraLabel()
        self.state_changed.emit()
    
    def onDeviceOpened(self):
        self.device_property_map = self.grabber.device_property_map

        self.device_property_map.set_value(ic4.PropId.OFFSET_AUTO_CENTER, 'Off')
        self.device_property_map.set_value(ic4.PropId.GAIN_AUTO, 'Off')
        self.device_property_map.set_value(ic4.PropId.GAIN, 0)
        self.device_property_map.set_value(ic4.PropId.EXPOSURE_AUTO, 'Off')
        self.device_property_map.set_value(ic4.PropId.PIXEL_FORMAT, 'Mono 16')
        self.width = self.device_property_map.get_value_int(ic4.PropId.WIDTH)
        self.height = self.device_property_map.get_value_int(ic4.PropId.HEIGHT)
        self.camera_opened.emit(
            self.device_property_map.get_value_int(ic4.PropId.WIDTH_MAX),
            self.device_property_map.get_value_int(ic4.PropId.HEIGHT_MAX),
            self.device_property_map.get_value_int(ic4.PropId.OFFSET_X),
            self.device_property_map.get_value_int(ic4.PropId.OFFSET_Y))

        self.updateCameraLabel()

        # if start_stream_on_open
        self.startStopStream()
    
    def customEvent(self, ev: QEvent):
        if ev.type() == DEVICE_LOST_EVENT:
            self.onDeviceLost()
    
    def updateCameraLabel(self):
        try:
            info = self.grabber.device_info
            self.camera_label.setText(f'{info.model_name} {info.serial}')
        except ic4.IC4Exception:
            self.camera_label.setText('No Device')
    
    def startStopStream(self):
        try:
            if self.grabber.is_device_valid:
                if self.grabber.is_streaming:
                    self.grabber.stream_stop()
                else:
                    self.grabber.stream_setup(self.sink)

        except ic4.IC4Exception as e:
            QMessageBox.critical(self, '', f'{e}', QMessageBox.StandardButton.Ok)

        self.state_changed.emit()