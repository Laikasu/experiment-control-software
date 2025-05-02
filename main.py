from PySide6.QtWidgets import QApplication

from multiprocessing import Process, Queue, set_start_method

import imagingcontrol4 as ic4
import os
from pymmcore_plus import CMMCorePlus
import numpy as np

from main_window import MainWindow

def setup_micromanager(mm_dir):
    application_path = os.path.abspath(os.path.dirname(__file__)) + os.sep
    
    mmc = CMMCorePlus.instance()
    mmc.setDeviceAdapterSearchPaths([mm_dir])
    mmc.loadSystemConfiguration(os.path.join(application_path, 'MMConfig.cfg'))
    return mmc

def move_stage(queue: Queue):
    mm_dir = 'C:/Program Files/Micro-Manager-2.0'
    mmc = setup_micromanager(mm_dir)

    while True:
        if not queue.empty():
            displacement = np.zeros(2)
            while not queue.empty():
                value = queue.get_nowait()
                displacement += value
            displacement_micron = 3.45*displacement/40
            mmc.setRelativeXYPosition(-displacement_micron[1], -displacement_micron[0])

def main():
    ic4.Library.init()
    
    app = QApplication()
    app.setApplicationName("monitor")
    app.setApplicationDisplayName("Monitor")
    app.setStyle("fusion")


    
    w = MainWindow()
    w.show()

    move_stage_queue = Queue()
    move_stage_process = Process(target=move_stage, args=(move_stage_queue,))
    move_stage_process.daemon = True
    w.move_stage.connect(move_stage_queue.put)
    move_stage_process.start()


    app.exec()
    ic4.Library.exit()
    

if __name__ == "__main__":
    main()