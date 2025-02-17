from PySide6.QtCore import QRect, QMargins, Qt, QPoint
from PySide6.QtGui import QPixmap, QImage, QPen
from PySide6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QGraphicsRectItem

import numpy as np

import imagingcontrol4 as ic4

class VideoView(QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self._current_frame = QGraphicsPixmapItem()
        self._frame = None
        self._scene.addItem(self._current_frame)
        self._rect = None
        self.roi = None
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

    def update_image(self, frame, roi):
        if self._frame is None:
            height, width, channels = np.shape(frame)
            self._frame = frame
        else:
            height, width, channels = np.shape(self._frame)
            if self.roi is not None:
                roi_index = np.index_exp[roi[1]:roi[3], roi[0]:roi[2]]
                self._frame[roi_index] = frame
                self._frame = np.ascontiguousarray(self._frame)
            else:
                self._frame = frame
            
        if frame.dtype == np.uint16:
            self._current_frame.setPixmap(QPixmap.fromImage(QImage(self._frame.data, width, height, 2*channels*width, QImage.Format_Grayscale16)))
        elif frame.dtype == np.uint8:
            self._current_frame.setPixmap(QPixmap.fromImage(QImage(self._frame.data, width, height, channels*width, QImage.Format_Grayscale8)))
        
    def set_roi(self, rect):
        if self.roi is None:
            self.roi = QGraphicsRectItem(rect)
            pen = QPen(Qt.red)
            pen.setWidth(2)
            self.roi.setPen(pen)
            self._scene.addItem(self.roi)
        else:
            self.roi.setRect(rect)
    
    def get_roi(self):
        if self.roi is None:
            return None
        else:
            return np.array(self.roi.rect().toRect().getCoords(), dtype=np.int16)

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
                self.start_point.setX(np.round(np.clip(self.start_point.x(), 0, self._current_frame.pixmap().width() - 1)/16)*16)
                self.start_point.setY(np.round(np.clip(self.start_point.y(), 0, self._current_frame.pixmap().height() - 1)/16)*16)
                rect = QRect(self.start_point, self.start_point)
                self.set_roi(rect)
        else:
            super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        if self.roi_mode:
            # Update the size of the rectangle as the mouse moves
            if self.start_point != None:
                end_point = self.mapToScene(event.pos()).toPoint()
                end_point.setX(np.round(np.clip(end_point.x(), 0, self._current_frame.pixmap().width() - 1)/16)*16)
                end_point.setY(np.round(np.clip(end_point.y(), 0, self._current_frame.pixmap().height() - 1)/16)*16)
                rect = QRect(self.start_point, end_point)#.normalized()  # Ensure correct rectangle direction
                self.set_roi(rect)
        return super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self.roi_mode:
                end_point = self.mapToScene(event.pos()).toPoint()
                end_point.setX(np.round(np.clip(end_point.x(), 0, self._current_frame.pixmap().width() - 1)/16)*16)
                end_point.setY(np.round(np.clip(end_point.y(), 0, self._current_frame.pixmap().height() - 1)/16)*16)
                rect = QRect(self.start_point, end_point)#.normalized()  # Ensure correct rectangle direction
                self.set_roi(rect)
                self.start_point = None  # Reset start point
        return super().mouseReleaseEvent(event)


    def reset_zoom(self):
        """
        Reset zoom to the original scale.
        """
        self.resetTransform()
        self.update_margins()
        self.current_scale = 1.0