from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import QFormLayout, QDoubleSpinBox, QDockWidget, QWidget, QSlider


class LaserWindow(QDockWidget):
    centerChanged = Signal(float)
    bandwidthChanged = Signal(float)
    powerChanged = Signal(int)
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.setWindowTitle("Laser Parameters")
        self._widget = QWidget(self)

        self.center = QDoubleSpinBox(singleStep=10, decimals=1, suffix=f" nm")
        self.center.valueChanged.connect(self.centerChanged)
        self.bandwidth = QDoubleSpinBox(minimum=10, singleStep=10, decimals=1, suffix=f" nm")
        self.bandwidth.valueChanged.connect(self.bandwidthChanged)
        self.power = QSlider(Qt.Orientation.Horizontal)
        self.power.valueChanged.connect(self.powerChanged)

        self.center.valueChanged.connect(self.update_wavelen)
        self.bandwidth.valueChanged.connect(self.update_bandwidth)

        layout = QFormLayout()
        layout.addRow("Center", self.center)
        layout.addRow("Bandwidth", self.bandwidth)
        layout.addRow("Power", self.power)

        self._widget.setLayout(layout)
        self.setWidget(self._widget)
    
    def update_bandwidth(self, bandwidth):
        self.center.setMinimum(390 + bandwidth/2)
        self.center.setMaximum(850 - bandwidth/2)

    def update_wavelen(self, wavelen):
        self.bandwidth.setMaximum(min((wavelen-390)*2, (850-wavelen)*2, 100))
    
    def set_values(self, wavelen, bandwidth, power):
        self.update_wavelen(wavelen)
        self.update_bandwidth(bandwidth)
        self.center.setValue(wavelen)
        self.bandwidth.setValue(bandwidth)
        self.power.setValue(power[1])