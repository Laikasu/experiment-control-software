from PySide6.QtWidgets import QApplication

import imagingcontrol4 as ic4

from mainwindow import MainWindow

def main():
    ic4.Library.init()
    app = QApplication()
    app.setApplicationName("monitor")
    app.setApplicationDisplayName("Monitor")
    app.setStyle("fusion")

    w = MainWindow()
    w.show()

    app.exec()
    ic4.Library.exit()
    

if __name__ == "__main__":
    main()