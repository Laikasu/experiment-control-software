import os
if os.name == 'nt':
    import NKTP_DLL as nkt

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QMessageBox

class Laser(QObject):
    changedState = Signal(bool)
    
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.open = False
        self.trigger_mode = 0 # Internal
        self.pulses = 10
        self.destroyed.connect(self.cleanup)
        if os.name == 'nt':
            self.grab(warning=False)
        else:
            QMessageBox.warning(self.parent(), 'Error', 'Failed opening laser: Linux/Mac are not supported due to the NKT laser only providing .dll')
        
    
    def set_emission(self, emit: bool):
        # Turn on
        nkt.registerWriteU8('COM4', 1, 0x30, emit, -1)

    def trigger(self):
        if self.open:
            #Trigger
            nkt.registerWriteU16('COM4', 1, 0x34, self.pulses, -1)
    
    def set_trigger_mode(self, mode):
        # Trigger if True else Internal
        self.trigger_mode = 2 if mode else 0
        if self.open:
            nkt.registerWriteU8('COM4', 1, 0x31, self.trigger_mode, -1)


    def grab(self, warning=True):
        result = nkt.openPorts('COM4', 1, 1)
        if result == 0:
            self.open = True
            # Unlock interlock
            nkt.registerWriteU16('COM4', 1, 0x32, 1, -1)
            # Trigger mode
            nkt.registerWriteU8('COM4', 1, 0x31, self.trigger_mode, -1)
            self.set_emission(True)
            lower = nkt.registerReadU16('COM4', 16, 0x34, -1)[1]/10
            higher = nkt.registerReadU16('COM4', 16, 0x33, -1)[1]/10
            self.bandwith = higher - lower
            self.wavelen = lower + self.bandwith/2
        else:
            self.open = False
            if warning:
                QMessageBox.warning(self.parent(),'Error', 'Failed opening laser: port busy.')
        self.changedState.emit(self.open)
    
    def release(self):
        self.set_emission(False)
        nkt.closePorts('COM4')
        self.open = False
        self.changedState.emit(self.open)
    
    def set_lower(self, wavelen: float):
        nkt.registerWriteU16('COM4', 16, 0x34, int(wavelen*10), -1)
    
    def set_upper(self, wavelen: float):
        nkt.registerWriteU16('COM4', 16, 0x33, int(wavelen*10), -1)
    
    def set_bandwith(self, width: float):
        self.bandwith = width
    
    def set_wavelen(self, wavelen):
        self.wavelen = wavelen
        self.set_lower(wavelen - self.bandwith/2)
        self.set_upper(wavelen + self.bandwith/2)
    
    def toggle_laser(self):
        if self.open:
            self.release()
        else:
            self.grab()
    
    def get_frequency(self) -> int:
        return nkt.registerReadU32('COM4', 1, 0x71, -1)[1]/1000
    
    

    def cleanup(self):
        if self.open:
            self.release()
            nkt.closePorts('COM4')
