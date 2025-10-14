from amfTools import AMF, Device
import amfTools
import logging
from PySide6.QtCore import QObject, Signal


class Pump(QObject):
    changedState = Signal(bool)
    open = False
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.amf = self.setup()
        self.destroyed.connect(self.cleanup)

    def setup(self):
        logging.debug('Looking for pump')
        device_list = amfTools.util.getProductList(connection_mode="USB/RS232", port="COM8")
        if len(device_list) > 0:
            logging.debug('Initializing pump')
            amf = AMF(product=device_list[0])
            if not amf.getHomeStatus():
                amf.home(False)
            amf.setSyringeSize(250)
            self.open = True
            return amf
        else:
            logging.debug('No pump found')
            # QMessageBox.warning(self, 'Error', f'failed to load pump')
            return None

    def toggle(self):
        if self.open:
            self.amf.disconnect()
            self.open = False
        else:
            if self.amf is not None:
                self.amf.connect()
                if not self.amf.getHomeStatus():
                    self.amf.home(False)
                self.open = True
            else:
                self.setup()
        self.changedState.emit(self.open)
    
    def cleanup(self):
        if self.open:
            self.amf.disconnect()