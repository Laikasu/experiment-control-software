from PySide6.QtCore import QRect, QMargins, Qt, QPoint, Signal
from PySide6.QtGui import QPixmap, QImage, QPen
from PySide6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QGraphicsRectItem

import numpy as np

import imagingcontrol4 as ic4

class VideoView(QGraphicsView):
    roi_set = Signal()
    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self._current_frame = QGraphicsPixmapItem()
        self._scene.addItem(self._current_frame)

        self.roi: QRect = None
        self.roi_graphic = QGraphicsRectItem()
        self.roi_graphic.setZValue(1)
        pen = QPen(Qt.red)
        pen.setWidth(2)
        self.roi_graphic.setPen(pen)
        self._scene.addItem(self.roi_graphic)

        self.setMinimumSize(640, 480)
        self.setScene(self._scene)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.zoom_factor = 1.25  # Zoom in/out factor
        self.current_scale = 1.0  # Track the current scale
        self.roi_mode = False
        self.start_point = None
    
    def set_size(self, width, height, offsetx, offsety):
        self.width = width
        self.height = height
        self.background = QGraphicsPixmapItem()
        image = QImage(self.width, self.height, QImage.Format_Grayscale16)
        image.fill(Qt.black)
        self.background.setPixmap(QPixmap.fromImage(image))
        self.background.setZValue(-1)
        self._scene.addItem(self.background)
        self._current_frame.setOffset(QPoint(offsetx, offsety))
        self.centerOn(self.background.boundingRect().center())
        self.scale(0.25,0.25)
        self.current_scale *= 0.25
        

    def update_image(self, frame):
        height, width, channels = np.shape(frame)
            
        if frame.dtype == np.uint16:
            self._current_frame.setPixmap(QPixmap.fromImage(QImage(frame.data, width, height, 2*channels*width, QImage.Format_Grayscale16)))
        elif frame.dtype == np.uint8:
            self._current_frame.setPixmap(QPixmap.fromImage(QImage(frame.data, width, height, channels*width, QImage.Format_Grayscale8)))
        
    def set_roi(self, rect):
        self.roi = rect
        self.roi_graphic.setRect(rect)

    def toggle_roi_mode(self):
        self.roi_mode = not self.roi_mode
        if self.roi_mode:
            self.setDragMode(QGraphicsView.NoDrag)
        else:
            self.setDragMode(QGraphicsView.ScrollHandDrag)

        

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
    
    def get_bounds(self):
        bounds = np.array(self.mapToScene(self.viewport().rect()).boundingRect().getCoords(), dtype=np.int16)
        bounds[0] = max(bounds[0], 0)
        bounds[1] = max(bounds[1], 0)
        bounds[2] = min(bounds[2], self._current_frame.pixmap().width() - 1)
        bounds[3] = min(bounds[3], self._current_frame.pixmap().height() - 1)
        return bounds
    
    def update_margins(self):
        if (not self.background.pixmap().isNull()):
            rect = self.mapToScene(self.viewport().rect()).boundingRect()
            size = rect.size()
            w = size.width() // 2
            h = size.height() // 2
            m = QMargins(w, h, w, h)
            rect = QRect(self.background.pixmap().rect().marginsAdded(m))
            self.setSceneRect(rect)
    
    def mousePressEvent(self, event):
        if self.roi_mode:
            # Start drawing a new rectangle
            if event.button() == Qt.LeftButton:
                self.start_point = self.mapToScene(event.pos()).toPoint()
                self.start_point.setX(np.round(np.clip(self.start_point.x(), 0, self.width)/16)*16)
                self.start_point.setY(np.round(np.clip(self.start_point.y(), 0, self.height)/16)*16)
                self.roi_graphic.show()
        else:
            super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        if self.roi_mode:
            # Update the size of the rectangle as the mouse moves
            if self.start_point != None:
                end_point = self.mapToScene(event.pos()).toPoint()
                end_point.setX(np.round(np.clip(end_point.x(), 0, self.width)/16)*16)
                end_point.setY(np.round(np.clip(end_point.y(), 0, self.height)/16)*16)
                rect = QRect(self.start_point, end_point).normalized()  # Ensure correct rectangle direction
                self.set_roi(rect)
        return super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self.roi_mode:
                end_point = self.mapToScene(event.pos()).toPoint()
                end_point.setX(np.round(np.clip(end_point.x(), 0, self.width)/16)*16 - 1)
                end_point.setY(np.round(np.clip(end_point.y(), 0, self.height)/16)*16 - 1)
                rect = QRect(self.start_point, end_point).normalized()  # Ensure correct rectangle direction
                self.set_roi(rect)

                # Stop roi_mode
                self.roi_graphic.hide()
                self.toggle_roi_mode()
                self.start_point = None  # Reset start point
                self._current_frame.setOffset(self.roi.topLeft())
                self.roi_set.emit()
        return super().mouseReleaseEvent(event)


    def reset_zoom(self):
        """
        Reset zoom to the original scale.
        """
        self.resetTransform()
        self.update_margins()
        self.current_scale = 1.0