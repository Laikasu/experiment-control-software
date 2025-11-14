from amfTools import AMF, Device
import amfTools
import logging
from PySide6.QtCore import QObject, Signal, QCoreApplication


class PumpController(QObject):
    changedState = Signal(bool)
    open = False
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.setup()
        self.destroyed.connect(self.cleanup)
        self.water = 10
        self.flowcell = 7
        self.waste = 1
        self.volume = 200

    def setup(self):
        logging.debug('Looking for pump')
        device_list = amfTools.util.getProductList(connection_mode="USB/RS232")
        if len(device_list) > 0:
            logging.debug('Initializing pump')
            amf = AMF(product=device_list[0])
            if not amf.getHomeStatus():
                amf.home(False)
            amf.setSyringeSize(250)

            self.amf = amf
            self.open = True
        else:
            logging.debug('No pump found')
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
    
    def pickup(self, port):
        if self.open:
            if port != self.waste and port != self.flowcell:
                self.amf.valveMove(port)
                self.amf.setFlowRate(1500,2)
                self.amf.pumpPickupVolume(self.volume)
            else:
                logging.error('Cannot pickup waste or flowcell!')
    
    def flow(self):
        if self.open:
            self.amf.setFlowRate(400,2)
            self.amf.valveMove(self.flowcell)
            self.amf.pumpDispenseVolume(self.volume,block=False)
    
    def wait_till_ready(self):
        if self.open:
            self.amf.pullAndWait()
    

    def clean_pump(self, ports):
        if self.open:
            volume = 500
            if self.waste not in ports and self.flowcell not in ports:
                self.amf.pullAndWait()
                self.amf.setFlowRate(1500,2)
                for i in range(5):
                    for output in ports:
                        self.amf.valveMove(self.water)
                        self.amf.pumpPickupVolume(volume)
                        self.amf.valveMove(output)
                        self.amf.pumpDispenseVolume(volume)
                        self.amf.pumpPickupVolume(volume)
                        self.amf.valveMove(self.waste)
                        self.amf.pumpDispenseVolume(volume)
            else:
                logging.error('Cannot pickup waste or flowcell!')