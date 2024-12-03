from PySide6.QtCore import QRectF, QMargins
from PySide6.QtGui import QPixmap, QImage
from PySide6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsPixmapItem

import numpy as np


class VideoView(QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self._current_frame = QGraphicsPixmapItem()
        self._scene.addItem(self._current_frame)
        self._rect = None
        self.setMinimumSize(640, 480)
        self.setScene(self._scene)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.zoom_factor = 1.25  # Zoom in/out factor
        self.current_scale = 1.0  # Track the current scale

    def update_image(self, frame):
        height, width, channels = np.shape(frame)
        if frame.dtype == np.uint16:
            self._current_frame.setPixmap(QPixmap.fromImage(QImage(frame.data, width, height, 2*channels*width, QImage.Format_Grayscale16)))
        elif frame.dtype == np.uint8:
            self._current_frame.setPixmap(QPixmap.fromImage(QImage(frame.data, width, height, channels*width, QImage.Format_Grayscale8)))
        

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

    def update_margins(self):
        if (not self._current_frame.pixmap().isNull()):
            rect = self.mapToScene(self.viewport().rect()).boundingRect()
            size = rect.size()
            w = size.width() // 2
            h = size.height() // 2
            m = QMargins(w, h, w, h)
            rect = QRectF(self._current_frame.pixmap().rect().marginsAdded(m))
            self.setSceneRect(rect)


    def reset_zoom(self):
        """
        Reset zoom to the original scale.
        """
        self.resetTransform()
        self.update_margins()
        self.current_scale = 1.0