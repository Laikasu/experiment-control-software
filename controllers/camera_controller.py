import imagingcontrol4 as ic4

from PySide6.QtCore import QStandardPaths, QTimer, QEvent, QFileInfo, Qt, Signal, QObject
from PySide6.QtWidgets import QApplication

import numpy as np

import logging

DEVICE_LOST_EVENT = QEvent.Type(QEvent.Type.User + 1)
    

class CameraController(QObject):
    new_frame = Signal(np.ndarray)
    state_changed = Signal()
    opened = Signal(int, int, int, int, int, int)
    label_update = Signal(str)
    statistics_update = Signal(str, str)

    def __init__(self, parent):
        super().__init__(parent)
        self.grabber = ic4.Grabber()
        self.grabber.event_add_device_lost(lambda g: QApplication.postEvent(self, QEvent(DEVICE_LOST_EVENT)))
        self.destroyed.connect(self.cleanup)
        self.property_dialog = None
        self.trigger_mode = False
        self.device_property_map = None

        self.update_statistics_timer = QTimer()
        self.update_statistics_timer.timeout.connect(self.update_statistics)
        self.update_statistics_timer.start()
        
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


    def reload_device(self):
        appdata_directory = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
        self.device_file = appdata_directory + '/device.json'
        if QFileInfo.exists(self.device_file):
            try:
                self.grabber.device_open_from_state_file(self.device_file)
                self.onDeviceOpened()
            except ic4.IC4Exception as e:
                logging.warning(f'Loading last used device failed: {e}')
    

    def cleanup(self):
        self.update_statistics_timer.stop()

        if self.grabber.is_device_valid:
            self.grabber.device_save_state_to_file(self.device_file)
        if self.grabber.is_streaming:
            self.grabber.stream_stop()
        
        if self.grabber.is_device_open:
            del(self.grabber)
            del(self.sink)
            if self.device_property_map is not None:
                del(self.device_property_map)
    

    def onCloseDevice(self):
        if self.grabber.is_streaming:
            self.startStopStream()
        
        try:
            self.grabber.device_close()
        except:
            pass

    
    def onSelectDevice(self):
        dlg = ic4.pyside6.DeviceSelectionDialog(self.grabber)
        if dlg.exec() == 1:
            if not self.property_dialog is None:
                self.property_dialog.update_grabber(self.grabber)
            
            self.onDeviceOpened()
    
    def onDeviceProperties(self):
        if self.property_dialog is None:
            self.property_dialog = ic4.pyside6.PropertyDialog(self.grabber, title='Device Properties')
            # set default vis
        
        self.property_dialog.show()
    
    def onDeviceDriverProperties(self, parent):
        dlg = ic4.pyside6.PropertyDialog(self.grabber.driver_property_map, parent=parent, title='Device Driver Properties')
        # set default vis

        dlg.exec()
    
    def update_statistics(self):
        if not self.grabber.is_device_valid:
            return
        try:
            stats = self.grabber.stream_statistics
            text = f'Frames Delivered: {stats.sink_delivered} Dropped: {stats.device_transmission_error}/{stats.device_underrun}/{stats.transform_underrun}/{stats.sink_underrun}'
            tooltip = (
                f'Frames Delivered: {stats.sink_delivered}'
                f'Frames Dropped:'
                f'  Device Transmission Error: {stats.device_transmission_error}'
                f'  Device Underrun: {stats.device_underrun}'
                f'  Transform Underrun: {stats.transform_underrun}'
                f'  Sink Underrun: {stats.sink_underrun}'
            )
            self.statistics_update.emit(text, tooltip)
        except ic4.IC4Exception:
            pass
    
    def onDeviceLost(self):
        logging.warning(f'The video capture device is lost!')

        # stop video

        self.updateCameraLabel()
        self.state_changed.emit()
    
    def trigger(self):
        if self.grabber.is_streaming:
            self.device_property_map.execute_command(ic4.PropId.TRIGGER_SOFTWARE)
    
    def set_trigger_mode(self, mode):
        self.trigger_mode = mode
        self.device_property_map.set_value(ic4.PropId.TRIGGER_MODE, mode)
    
    def onDeviceOpened(self):
        self.device_property_map = self.grabber.device_property_map
        self.device_property_map.set_value(ic4.PropId.TRIGGER_MODE, False)
        self.device_property_map.set_value(ic4.PropId.OFFSET_AUTO_CENTER, 'Off')
        self.device_property_map.set_value(ic4.PropId.GAIN_AUTO, 'Off')
        self.device_property_map.set_value(ic4.PropId.GAIN, 0)
        self.device_property_map.set_value(ic4.PropId.EXPOSURE_AUTO, 'Off')
        self.device_property_map.set_value(ic4.PropId.PIXEL_FORMAT, 'Mono16')

        self.roi_width = self.device_property_map.get_value_int(ic4.PropId.WIDTH)
        self.roi_height = self.device_property_map.get_value_int(ic4.PropId.HEIGHT)
        self.opened.emit(
            self.roi_width,
            self.roi_height,
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
            self.label_update.emit(f'{info.model_name} {info.serial}')
        except ic4.IC4Exception:
            self.label_update.emit('No Device')
    
    def startStopStream(self):
        try:
            if self.grabber.is_device_valid:
                if self.grabber.is_streaming:
                    self.grabber.stream_stop()
                else:
                    self.grabber.stream_setup(self.sink)

        except ic4.IC4Exception as e:
            logging.error(f'{e}')

        self.state_changed.emit()
    
    def get_exposure_auto(self):
        return self.device_property_map.get_value_bool(ic4.PropId.EXPOSURE_AUTO)

    def get_exposure_time(self):
        return int(self.device_property_map.get_value_float(ic4.PropId.EXPOSURE_TIME))
    
    def get_fps(self):
        return self.device_property_map.get_value_float(ic4.PropId.ACQUISITION_FRAME_RATE)
    
    def set_roi(self, roi):
        self.startStopStream()
        self.roi_width = int(roi.width())
        self.roi_height = int(roi.height())
        self.device_property_map.set_value(ic4.PropId.WIDTH, int(roi.width()))
        self.device_property_map.set_value(ic4.PropId.HEIGHT, int(roi.height()))
        self.device_property_map.set_value(ic4.PropId.OFFSET_X, int(roi.left()))
        self.device_property_map.set_value(ic4.PropId.OFFSET_Y, int(roi.top()))
        self.startStopStream()
    
    def set_autoexposure(self, value: str):
        self.device_property_map.set_value(ic4.PropId.EXPOSURE_AUTO, value)