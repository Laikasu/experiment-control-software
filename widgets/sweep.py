from PySide6.QtCore import Signal, QRegularExpression
from PySide6.QtWidgets import QFormLayout, QDoubleSpinBox, QSpinBox, QDockWidget, QWidget, QPushButton, QCheckBox, QGroupBox, QVBoxLayout, QLineEdit
from PySide6.QtGui import QRegularExpressionValidator

class SweepWindow(QDockWidget):
    start_acquisition = Signal(dict)
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.setWindowTitle("Acquisitions")
        self._widget = QWidget(self)


        # Laser
        self.laser_sweep = QCheckBox()
        self.laser_sweep.toggled.connect(self.update_controls)
        self.laser_start = QDoubleSpinBox(singleStep=10, decimals=1, suffix=f" nm")
        self.laser_stop = QDoubleSpinBox(minimum=10, singleStep=10, decimals=1, suffix=f" nm")
        self.laser_num = QSpinBox(minimum=1, singleStep=10, value=10)

        # Defocus
        self.defocus_sweep = QCheckBox()
        self.defocus_sweep.toggled.connect(self.update_controls)
        self.defocus_start = QDoubleSpinBox(singleStep=10, decimals=1, suffix=f" nm")
        self.defocus_stop = QDoubleSpinBox(minimum=10, singleStep=10, decimals=1, suffix=f" nm")
        self.defocus_num = QSpinBox(minimum=1, singleStep=10, value=10)


        # Media
        self.media_sweep = QCheckBox()
        self.media_sweep.toggled.connect(self.update_controls)
        self.media = QLineEdit()
        validator = QRegularExpressionValidator(QRegularExpression(r"^\d*$"))
        self.media.setValidator(validator)

        self.startButton = QPushButton('Start')
        self.startButton.clicked.connect(self.sweep)


        
        laser_group = QGroupBox("Wavelength")
        layout = QFormLayout()
        layout.addRow("Enable", self.laser_sweep)
        layout.addRow("Start", self.laser_start)
        layout.addRow("Stop", self.laser_stop)
        layout.addRow("Num", self.laser_num)
        laser_group.setLayout(layout)

        defocus_group = QGroupBox("Defocus")
        layout = QFormLayout()
        layout.addRow("Enable", self.defocus_sweep)
        layout.addRow("Start", self.defocus_start)
        layout.addRow("Stop", self.defocus_stop)
        layout.addRow("Num", self.defocus_num)
        defocus_group.setLayout(layout)

        media_group = QGroupBox("Medium")
        layout = QFormLayout()
        layout.addRow("Enable", self.media_sweep)
        layout.addRow("Media", self.media)
        media_group.setLayout(layout)


        layout = QVBoxLayout()
        layout.addWidget(laser_group)
        layout.addWidget(defocus_group)
        layout.addWidget(media_group)
        layout.addWidget(self.startButton)
        layout.addStretch(-1)
        self._widget.setLayout(layout)

        self.setWidget(self._widget)
        self.update_controls()
    
    def update_controls(self):
        laser = self.laser_sweep.isChecked()
        defocus = self.defocus_sweep.isChecked()
        media = self.media_sweep.isChecked()
        self.laser_start.setEnabled(laser)
        self.laser_stop.setEnabled(laser)
        self.laser_num.setEnabled(laser)

        self.defocus_start.setEnabled(defocus)
        self.defocus_stop.setEnabled(defocus)
        self.defocus_num.setEnabled(defocus)

        self.media.setEnabled(media)

        self.startButton.setEnabled(laser or defocus or media)


    def sweep(self):
        params = dict()
        if self.media_sweep.isChecked():
            media = [int(char) for char in self.media.text()]
            params['media'] = media

        if self.defocus_sweep.isChecked():
            z_positions = (self.defocus_start.value(), self.defocus_stop.value(), self.defocus_num.value())
            params['defocus'] = z_positions
        
        if self.laser_sweep.isChecked():
            wavelens = (self.defocus_start.value(), self.defocus_stop.value(), self.defocus_num.value())
            params['wavelens'] = wavelens
        
        self.start_acquisition.emit(params)