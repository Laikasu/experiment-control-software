# Stage
from pymmcore_plus import CMMCorePlus
import logging
from pathlib import Path

class StageController():
    def __init__(self):
        self.open = False
        self.setup_micromanager()

    def setup_micromanager(self):
        self.mmc = CMMCorePlus.instance()
        # Load config
        try:
            self.mmc.loadSystemConfiguration(Path(__file__) / 'MMConfig.cfg')
        except Exception as e:
            logging.warning(f'failed to load mm config: \n{e}')
        else:
            self.open = True
            self.z_stage = self.mmc.getFocusDevice()
            self.xy_stage = self.mmc.getXYStageDevice()
            logging.debug('Connected to micromanager')

    def set_xy_position(self, pos):
        if self.open:
            self.mmc.setXYPosition(pos[0], pos[1])
            self.mmc.waitForDevice(self.xy_stage)

    def get_xy_position(self):
        if self.open:
            return self.mmc.getXYPosition()
    
    def set_z_position(self, pos):
        if self.open:
            self.mmc.setZPosition(pos)
            self.mmc.waitForDevice(self.z_stage)

    def get_z_position(self):
        if self.open:
            return self.mmc.getZPosition()
    
    def move_stage(self, displacement):
        if self.open:
            displacement_micron = 3.45*displacement/60
            self.mmc.setRelativeXYPosition(-displacement_micron[1], -displacement_micron[0])