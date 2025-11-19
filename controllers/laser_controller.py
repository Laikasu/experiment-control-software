import os
if os.name == 'nt':
    import NKTP_DLL as nkt

import logging

def requires_open(method):
    def wrapper(self, *args, **kwargs):
        if self.open:
            return method(self, *args, **kwargs)
        else:
            raise RuntimeError("Device is not open, cannot call this method.")
    return wrapper

from PySide6.QtCore import QObject, Signal

class LaserController(QObject):
    changedState = Signal(bool)
    
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.open = False
        self.trigger_mode = 0 # Internal
        self.pulses = 10
        self.port = None
        
        self.grab(warning=False)
        
    @requires_open
    def set_emission(self, emit: bool):
        # Turn on
        nkt.registerWriteU8(self.port, 1, 0x30, emit, -1)
    
    @requires_open
    def trigger(self):
        #Trigger
        nkt.registerWriteU16(self.port, 1, 0x34, self.pulses, -1)
    
    @requires_open
    def set_trigger_mode(self, mode):
        # Trigger if True else Internal
        self.trigger_mode = 2 if mode else 0
        nkt.registerWriteU8(self.port, 1, 0x31, self.trigger_mode, -1)


    def grab(self, warning=True):
        logging.debug('Opening laser')
        if os.name != 'nt':
            if warning:
                logging.warning('Failed opening laser: Linux/Mac are not supported due to the NKT laser only providing .dll')
            logging.debug("Failed opening laser: Wrong OS")
            self.changedState.emit(self.open)
            return
        ports = nkt.getAllPorts()
        result = nkt.openPorts(ports, 1, 1)
        
        if result == 0:
            self.open = True
            logging.debug('Laser connected')
            self.port = nkt.getOpenPorts()
            # Unlock interlock
            nkt.registerWriteU16(self.port, 1, 0x32, 1, -1)
            # Trigger mode
            nkt.registerWriteU8(self.port, 1, 0x31, self.trigger_mode, -1)
            self.set_emission(True)
            lower = nkt.registerReadU16(self.port, 16, 0x34, -1)[1]/10
            higher = nkt.registerReadU16(self.port, 16, 0x33, -1)[1]/10
            self.bandwith = higher - lower
            self.wavelen = lower + self.bandwith/2
        else:
            logging.debug('Failed opening laser: Port busy')
            self.open = False
            if warning:
                logging.warning('Failed opening laser: Port busy')
        self.changedState.emit(self.open)
    
    @requires_open
    def release(self):
        logging.debug('Laser disconnected')
        self.set_emission(False)
        nkt.closePorts(self.port)
        self.open = False
        self.changedState.emit(self.open)
    
    @requires_open
    def set_lower(self, wavelen: float):
        nkt.registerWriteU16(self.port, 16, 0x34, int(wavelen*10), -1)
    
    @requires_open
    def set_upper(self, wavelen: float):
        nkt.registerWriteU16(self.port, 16, 0x33, int(wavelen*10), -1)
    
    @requires_open
    def update_bounds(self):
        self.set_lower(self.wavelen - self.bandwith/2)
        self.set_upper(self.wavelen + self.bandwith/2)
    
    @requires_open
    def set_bandwith(self, width: float):
        self.bandwith = width
        self.update_bounds()
    
    @requires_open
    def set_wavelen(self, wavelen):
        self.wavelen = wavelen
        self.update_bounds()
        
    
    def toggle_laser(self):
        if self.open:
            self.release()
        else:
            self.grab()
    
    @requires_open
    def get_frequency(self) -> int:
        return nkt.registerReadU32(self.port, 1, 0x71, -1)[1]/1000
    
    @requires_open
    def set_power(self, percentage):
        nkt.registerWriteU8(self.port, 1, 0x3E, int(percentage), -1)

    @requires_open
    def get_power(self):
        return nkt.registerReadU8(self.port, 1, 0x3E, -1)
    
    
    def cleanup(self):
        if self.open:
            self.release()