from PySide6.QtWidgets import QApplication

import imagingcontrol4 as ic4

from mainwindow import MainWindow

def main():
    with ic4.Library.init_context():
        app = QApplication()
        app.setApplicationName("monitor")
        app.setApplicationDisplayName("Monitor")
        app.setStyle("fusion")

        w = MainWindow()
        w.show()

        app.exec()

if __name__ == "__main__":
    main()