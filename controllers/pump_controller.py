from amfTools import AMF, Device
import amfTools
import logging
from PySide6.QtCore import QObject, Signal, QCoreApplication


class PumpController(QObject):
    changedState = Signal(bool)
    open = False
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.destroyed.connect(self.cleanup)
        self.amf = None
        self.water = 1
        self.flowcell = 8
        self.waste = 10
        self.setup()

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
        if self.amf is not None:
            #  Reconnect
            if not self.open:
                self.amf.connect()
                if not self.amf.getHomeStatus():
                    self.amf.home(False)
                self.open = True
            else:
                self.amf.disconnect()
                self.open = False
        else:
            self.setup()
            
        self.changedState.emit(self.open)
    
    def cleanup(self):
        if self.open and self.amf is not None:
            self.amf.disconnect()
    
    def pickup(self, port, volume=200):
        logging.debug(f'Picking up {volume}uL from port {port}')
        if self.open and self.amf is not None:
            if not self.amf.getHomeStatus():
                    self.amf.home(False)
            if port != self.waste and port != self.flowcell:
                self.amf.valveMove(port)
                self.amf.setFlowRate(1500,2)
                self.amf.pumpPickupVolume(volume, block=False)
            else:
                logging.error('Cannot pickup waste or flowcell!')
    
    def dispense(self, port, volume=200):
        logging.debug(f'Dispensing {volume}uL to port {port}')
        if self.open and self.amf is not None:
            if not self.amf.getHomeStatus():
                self.amf.home(False)
            if port != self.water:
                self.amf.valveMove(port)
                if port == self.flowcell:
                    self.amf.setFlowRate(100,2)
                else:
                    self.amf.setFlowRate(1500,2)
                self.amf.pumpDispenseVolume(volume, block=False)
            else:
                logging.error('Cannot dispense in water!')
    
    def flow(self, volume=40):
        logging.debug(f'Dispensing {volume}uL to flowcell')
        if self.open and self.amf is not None:
            if not self.amf.getHomeStatus():
                    self.amf.home(False)
            self.amf.setFlowRate(100,2)
            self.amf.valveMove(self.flowcell)
            self.amf.pumpDispenseVolume(volume,block=False)
    
    def wait_till_ready(self):
        if self.open and self.amf is not None:
            self.amf.pullAndWait()
    

    def clean_pump(self, ports):
        if self.open and self.amf is not None:
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