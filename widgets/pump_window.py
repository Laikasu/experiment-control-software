from PySide6.QtCore import Signal, QRegularExpression
from PySide6.QtWidgets import QFormLayout, QSpinBox, QDockWidget, QWidget, QPushButton, QCheckBox, QGroupBox, QVBoxLayout, QLineEdit, QComboBox, QButtonGroup, QHBoxLayout
from PySide6.QtGui import QRegularExpressionValidator

class PumpWindow(QDockWidget):
    start_dispense = Signal(int, int)
    start_pickup = Signal(int, int)
    start_clean = Signal(list[int])
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.setWindowTitle("Pump")
        self._widget = QWidget(self)


        
        self.port = QComboBox()
        self.port.addItems(['1: Waste', '2', '3', '4', '5', '6', '7: Flowcell', '8', '9', '10: Water'])
        self.port.currentTextChanged.connect(self.update_controls)

        self.volume = QSpinBox(minimum=0, maximum=250, singleStep=10, suffix = 'uL')
        self.volume.setValue(100)


        self.pickup_button = QPushButton('Pickup')
        self.dispense_button = QPushButton('Dispense')

        button_layout = QHBoxLayout(self)
        button_layout.addWidget(self.pickup_button)
        button_layout.addWidget(self.dispense_button)
        


        self.clean_ports = QLineEdit()
        validator = QRegularExpressionValidator(QRegularExpression(r"^\d*$"))
        self.clean_ports.setValidator(validator)
        self.clean_button = QPushButton("Clean")
        clean_layout = QVBoxLayout()
        clean_layout.addWidget(self.clean_ports)
        clean_layout.addWidget(self.clean_button)

        main_layout = QVBoxLayout()
        layout = QFormLayout()
        layout.addRow("Port", self.port)
        layout.addRow("Volume", self.volume)

        main_layout.addLayout(layout)
        main_layout.addLayout(button_layout)
        main_layout.addLayout(clean_layout)
        main_layout.addStretch(-1)

        self._widget.setLayout(main_layout)

        self.setWidget(self._widget)
    
    def update_controls(self, port):
        self.dispense_button.setEnabled(True)
        self.pickup_button.setEnabled(True)
        if 'Water' in port:
            self.dispense_button.setEnabled(False)
        
        if 'Waste' in port or 'Flowcell' in port:
            self.pickup_button.setEnabled(False)
    
    def dispense(self):
        self.start_dispense.emit(self.port.currentIndex() + 1, self.volume.value())
    
    def pickup(self):
        self.start_pickup.emit(self.port.currentIndex() + 1, self.volume.value())
    
    def clean(self):
        ports = set(int(i) for i in self.clean_ports.text())
        ports.discard(1)
        ports.discard(7)
        ports.discard(0)
        self.start_clean.emit(ports)