import NKTP_DLL as nkt

class Laser():
    def __init__(self):
        nkt.openPorts('COM4', 1, 1)
        self.bandwith = 50
    
    def set_emission(self, emit: bool):
        nkt.registerWriteU8('COM4', 1, 0x30, emit, -1)
    
    def set_lower(self, wavelen: float):
        nkt.registerWriteU16('COM4', 16, 0x34, int(wavelen*10), -1)
    
    def set_upper(self, wavelen: float):
        nkt.registerWriteU16('COM4', 16, 0x33, int(wavelen*10), -1)
    
    def set_bandwith(self, width: float):
        self.bandwith = width
    
    def set_middle(self, wavelen):
        self.set_lower(wavelen - self.bandwith/2)
        self.set_upper(wavelen + self.bandwith/2)

    def __del__(self):
        nkt.closePorts('COM4')