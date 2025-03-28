from PySide6.QtCore import QRect, QMargins, Qt, QPoint, Signal
from PySide6.QtGui import QPixmap, QImage, QPen, QBrush
from PySide6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QGraphicsRectItem, QDialog, QFormLayout, QSpinBox, QDoubleSpinBox, QVBoxLayout, QHBoxLayout, QPushButton, QDialogButtonBox

import numpy as np

class SweepDialog(QDialog):
    def __init__(self, parent, title: str, limits, defaults, unit):
        super().__init__(parent=parent)
        self.setWindowTitle(title)

        self.start = QDoubleSpinBox(minimum=limits[0], maximum=limits[1], singleStep=10, decimals=1, suffix=f" {unit}")
        self.start.setValue(defaults[0])
        self.end = QDoubleSpinBox(minimum=limits[2], maximum=limits[3], singleStep=10, decimals=1, suffix=f" {unit}")
        self.end.setValue(defaults[1])
        self.number = QSpinBox(minimum=10, maximum=200, singleStep=10)
        self.number.setValue(defaults[2])
        layout = QFormLayout()
        layout.addRow("Start", self.start)
        layout.addRow("End", self.end)
        layout.addRow("Number", self.number)

        # Buttons
        self.cancel_button = QPushButton("Cancel")
        self.submit_button = QPushButton("Start")

        self.button_box = QDialogButtonBox( QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

        dialog_layout = QVBoxLayout()
        dialog_layout.addLayout(layout)
        dialog_layout.addWidget(self.button_box)
        self.setLayout(dialog_layout)
    
    def get_values(self):
        return self.start.value(), self.end.value(), self.number.value()

class VideoView(QGraphicsView):
    roi_set = Signal(QRect)
    move_stage = Signal(np.ndarray)
    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        
        self.camera_display = QGraphicsPixmapItem()
        self._scene.addItem(self.camera_display)

        self.background = QGraphicsRectItem()
        self.background.setZValue(-1)
        self.background.setBrush(QBrush(Qt.black))
        self._scene.addItem(self.background)

        self.roi_graphic = QGraphicsRectItem()
        self.roi_graphic.setZValue(1)
        self.roi_graphic.setPen(QPen(Qt.red, 2))
        self._scene.addItem(self.roi_graphic)

        self.setMinimumSize(640, 480)
        self.setScene(self._scene)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)

        self.zoom_factor = 1.25
        self.current_scale = 1.0
        self.start_point = None
        self.displacement_thresh = 10

        self._mode = "navigation"
    
    @property
    def mode(self) -> str:
        return self._mode
    
    @mode.setter
    def mode(self, new_mode: str):
        if (new_mode == "navigation" or new_mode =="move"):
            self.setDragMode(QGraphicsView.ScrollHandDrag)
        elif (new_mode == "roi"):
            self.setDragMode(QGraphicsView.NoDrag)
        else:
            raise ValueError(f"Unexpected input: mode {new_mode} unknown")
        self._mode = new_mode

        

    
    def set_size(self, width: int, height: int, max_width: int, max_height: int, offset_x: int, offset_y: int):
        self.max_roi_width = max_width
        self.max_roi_height = max_height
        self.background.setRect(QRect(0, 0, max_width, max_height))
        self.camera_display.setOffset(QPoint(offset_x, offset_y))
        self.scale(0.25,0.25)
        self.current_scale *= 0.25
        self.update_margins()
        self.centerOn(self.background.boundingRect().center())
        

    def update_image(self, frame):
        height, width, channels = np.shape(frame)
            
        if frame.dtype == np.uint16:
            self.camera_display.setPixmap(QPixmap.fromImage(QImage(frame.data, width, height, 2*channels*width, QImage.Format_Grayscale16)))
        elif frame.dtype == np.uint8:
            self.camera_display.setPixmap(QPixmap.fromImage(QImage(frame.data, width, height, channels*width, QImage.Format_Grayscale8)))

        

    def wheelEvent(self, event):
        """
        Override the wheelEvent to zoom in or out.
        """
        # if event.modifiers() & Qt.ControlModifier:  # Check if Ctrl is held
        if event.angleDelta().y() > 0:  # Scroll up to zoom in
            self.zoom_in()
        else:  # Scroll down to zoom out
            self.zoom_out()
        # else:
        #     # Pass the event to the parent class for default behavior (e.g., scrolling)
        #super().wheelEvent(event)
    
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_margins()

    def zoom_in(self):
        """
        Zoom in by scaling up.
        """
        self.scale(self.zoom_factor, self.zoom_factor)
        self.current_scale *= self.zoom_factor
        self.update_margins()

    def zoom_out(self):
        """
        Zoom out by scaling down.
        """
        self.scale(1 / self.zoom_factor, 1 / self.zoom_factor)
        self.current_scale /= self.zoom_factor
        self.update_margins()
    
    def reset_zoom(self):
        """
        Reset zoom to the original scale.
        """
        self.resetTransform()
        self.update_margins()
        self.current_scale = 1.0
    
    def get_bounds(self):
        bounds = np.array(self.mapToScene(self.viewport().rect()).boundingRect().getCoords(), dtype=np.int16)
        bounds[0] = max(bounds[0], 0)
        bounds[1] = max(bounds[1], 0)
        bounds[2] = min(bounds[2], self.camera_display.pixmap().width() - 1)
        bounds[3] = min(bounds[3], self.camera_display.pixmap().height() - 1)
        return bounds
    
    def update_margins(self):
        """
        Make margins of half the viewport size around the camera to enable panning up to the borders
        """
        rect = self.mapToScene(self.viewport().rect()).boundingRect()
        size = rect.size()
        w = size.width() // 2
        h = size.height() // 2
        m = QMargins(w, h, w, h)
        rect = self.background.rect().marginsAdded(m).toRect()
        self.setSceneRect(rect)
    
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self.mode == "move":
                self.start_point = self.mapToScene(event.pos())
            if self.mode == "roi":
                # Start drawing a new rectangle
                self.start_point = self.mapToScene(event.pos()).toPoint()
                self.start_point.setX(np.round(np.clip(self.start_point.x(), 0, self.max_roi_width)/16)*16)
                self.start_point.setY(np.round(np.clip(self.start_point.y(), 0, self.max_roi_height)/16)*16)
                self.roi_graphic.show()
            if self.mode == "navigation":
                super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        if self.start_point is not None:
            if self.mode == "move":
                current_point = self.mapToScene(event.pos())
                displacement = current_point - self.start_point
                if (displacement.x()**2 + displacement.y()**2) > self.displacement_thresh:
                    self.start_point = current_point
                    self.move_stage.emit(np.array(displacement.toTuple()))

            if self.mode == "roi":
                # Update the graphic
                end_point = self.mapToScene(event.pos()).toPoint()
                end_point = self.calculate_endpoint(end_point)
                rect = QRect(self.start_point, end_point).normalized()
                self.roi_graphic.setRect(rect)
        return super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self.start_point is not None:
                if self.mode == "move":
                    self.start_point = None
                if self.mode == "roi":
                    # Update the graphic
                    end_point = self.mapToScene(event.pos()).toPoint()
                    end_point = self.calculate_endpoint(end_point)
                    end_point.setX(end_point.x()-1)
                    end_point.setY(end_point.y()-1)
                    rect = QRect(self.start_point, end_point).normalized()
                    # Update roi and turn off roi mode
                    self.mode = "navigation"
                    self.start_point = None  # Reset start point
                    self.roi_set.emit(rect)
                    self.roi_graphic.hide()
                    self.camera_display.setOffset(rect.topLeft())
        return super().mouseReleaseEvent(event)

    def calculate_endpoint(self, end_point):
        # Snap to grid
        end_point.setX(np.round(np.clip(end_point.x(), 0, self.max_roi_width)/16)*16)
        end_point.setY(np.round(np.clip(end_point.y(), 0, self.max_roi_height)/16)*16)

        # Set minimum to 256
        displacement = end_point - self.start_point
        if displacement.x() < 256 and displacement.x() >= 0:
            displacement.setX(256)
        elif displacement.x() > -256 and displacement.x() < 0:
            displacement.setX(-256)
        if displacement.y() < 256 and displacement.y() >= 0:
            displacement.setY(256)
        elif displacement.y() > -256 and displacement.y() < 0:
            displacement.setY(-256)
        
        # Bound within picture
        end_point = self.start_point + displacement
        if end_point.x() < 0:
            end_point.setX(end_point.x() + 512)
        elif end_point.x() > self.max_roi_width:
            end_point.setX(end_point.x() - 512)
        if end_point.y() < 0:
            end_point.setY(end_point.y() + 512)
        elif end_point.y() > self.max_roi_height:
            end_point.setY(end_point.y() - 512)
        
        return end_point