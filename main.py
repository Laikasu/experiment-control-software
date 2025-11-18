from PySide6.QtWidgets import QApplication, QMessageBox

import imagingcontrol4 as ic4

import sys
import traceback

from main_window import MainWindow
from main_controller import MainController

def excepthook(exc_type, exc_value, exc_traceback):
    # Print to console
    traceback.print_exception(exc_type, exc_value, exc_traceback)
    # Optional: show a message box
    msg = QMessageBox()
    msg.setIcon(QMessageBox.Icon.Critical)
    msg.setWindowTitle("Error")
    msg.setText(f"{exc_type.__name__}: {exc_value}")
    msg.exec()

sys.excepthook = excepthook

def main():
    ic4.Library.init()
    app = QApplication()
    app.setApplicationName("experiment-control-software")
    app.setApplicationDisplayName("Experiment Control Software")
    app.setStyle("fusion")

    controller = MainController()
    w = MainWindow(controller)
    w.show()

    app.exec()
    del(controller)
    ic4.Library.exit()
    

if __name__ == "__main__":
    main()