from PySide6.QtCore import Qt, Signal, QPointF
from PySide6.QtGui import QImage, QMouseEvent, QPixmap, QPainter, QNativeGestureEvent
from PySide6.QtWidgets import QGraphicsPixmapItem, QGraphicsScene, QGraphicsView
import numpy as np
from enum import StrEnum

from ...stars.star_data import StarCatalog


class StarDisplayMode(StrEnum):
    NONE = "none"
    ALL = "all"
    ALIGNMENT = "alignment"


class ImageViewer(QGraphicsView):
    zoom_changed = Signal(float)

    def __init__(self):
        super().__init__()
        self.scene = QGraphicsScene()
        self.setScene(self.scene)
        self.setBackgroundBrush(Qt.GlobalColor.black)
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        self._pixmap_item: QGraphicsPixmapItem | None = None
        self._all_stars: StarCatalog | None = None
        self._alignment_stars: StarCatalog | None = None
        self._star_display_mode = StarDisplayMode.NONE

        self._display_scale_x = 1.0
        self._display_scale_y = 1.0

        # ドラッグで移動
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)

        # アンカーをマウス位置へ
        self.setTransformationAnchor(
            QGraphicsView.ViewportAnchor.AnchorUnderMouse
        )
        self.setResizeAnchor(
            QGraphicsView.ViewportAnchor.AnchorUnderMouse
        )
        self._fit_mode = True

    def set_star_display_mode(self, mode: StarDisplayMode):
        self._star_display_mode = mode
        self.viewport().update()

    def drawForeground(self, painter: QPainter, rect):
        super().drawForeground(painter, rect)
        if self._pixmap_item is None:
            return
        if self._star_display_mode == StarDisplayMode.NONE:
            return

        if self._star_display_mode == StarDisplayMode.ALL:
            catalog = self._all_stars
        else:
            catalog = self._alignment_stars

        if catalog is None: return

        radius = 8

        pen = painter.pen()
        if self._star_display_mode == StarDisplayMode.ALL:
            pen.setColor(Qt.GlobalColor.yellow)
        else:
            pen.setColor(Qt.GlobalColor.red)
        painter.setPen(pen)

        for star in catalog.stars:
            x = star.x * self._display_scale_x
            y = star.y * self._display_scale_y
            painter.drawEllipse(
                QPointF(x, y),
                radius,
                radius,
            )

    
    def fit_image(self):
        if self._pixmap_item is None:
            return

        self.fitInView(
            self.scene.sceneRect(),
            Qt.AspectRatioMode.KeepAspectRatio
        )

        self._fit_mode = True
        self.zoom_changed.emit(
            self.zoom_percent()
        )

    def zoom_percent(self) -> float:
        return round(self.transform().m11() * 100)
    
    def set_zoom(self, percent: float):
        if self._pixmap_item is None:
            return

        scale = percent / 100

        self.resetTransform()
        self.scale(scale, scale)

        self._fit_mode = False
        self.zoom_changed.emit(
            self.zoom_percent()
        )


    def set_image(self, image: np.ndarray | None, all_stars: StarCatalog | None = None, alignment_stars: StarCatalog | None = None, star_scale_x: float = 1.0, star_scale_y: float = 1.0) -> None:
        self._all_stars = all_stars
        self._alignment_stars = alignment_stars
        self._display_scale_x = star_scale_x
        self._display_scale_y = star_scale_y
        need_fits_image = False
        if self._pixmap_item is None: need_fits_image = True
        # self.scene.clear()
        if self._pixmap_item is not None:
            self.scene.removeItem(self._pixmap_item)
        self._pixmap_item = None
        if image is None:
            self.viewport().update()
            return
        qimage = self._to_qimage(image)
        self._pixmap_item = self.scene.addPixmap(QPixmap.fromImage(qimage))
        self.scene.setSceneRect(self._pixmap_item.boundingRect())
        if need_fits_image: self.fit_image()
        self.viewport().update()


    def resizeEvent(self, event):
        super().resizeEvent(event)

        if self._pixmap_item is None:
            return

        # 全体表示中だけ再Fit
        if self._fit_mode:
            self.fit_image()

    
    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        self.fit_image()
        super().mouseDoubleClickEvent(event)


    def event(self, event):
        if isinstance(event, QNativeGestureEvent):
            if (
                event.gestureType()
                == Qt.NativeGestureType.ZoomNativeGesture
            ):
                self.zoom_by_factor(1.0 + event.value())
                return True

        return super().event(event)
    


    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_0:
            self.fit_image()
        elif event.key() == Qt.Key.Key_1:
            self.set_zoom(100)

        super().keyPressEvent(event)

    def _to_qimage(self, image: np.ndarray) -> QImage:
        arr = np.squeeze(np.asarray(image, dtype=np.float32))
        finite = arr[np.isfinite(arr)]
        if finite.size == 0:
            arr = np.zeros_like(arr, dtype=np.float32)
        else:
            bg = np.median(finite)
            sigma = np.std(finite)
            stretch = 5
            arr = np.clip(arr - bg + 3 * sigma, 0, None)
            arr = np.arcsinh(arr / (stretch * sigma))
            arr /= arr.max() + 1e-8
            # arr = arr ** (1 / 2.2)
            arr = np.power(arr, 0.7)
        arr8 = (arr * 255).round().astype(np.uint8)
        if arr8.ndim == 2:
            h, w = arr8.shape
            return QImage(arr8.data, w, h, w, QImage.Format.Format_Grayscale8).copy()
        if arr8.shape[2] == 1:
            arr8 = arr8[..., 0]
            h, w = arr8.shape
            return QImage(arr8.data, w, h, w, QImage.Format.Format_Grayscale8).copy()
        if arr8.shape[2] > 3:
            arr8 = arr8[..., :3]
        h, w, _ = arr8.shape
        return QImage(arr8.data, w, h, 3 * w, QImage.Format.Format_RGB888).copy()
    


    def wheelEvent(self, event):
        if self._pixmap_item is None:
            return

        if event.angleDelta().y() > 0:
            self.zoom_by_factor(1.25)
        else:
            self.zoom_by_factor(0.8)

    
    def zoom_by_factor(self, factor):
        if self._pixmap_item is None:
            return

        self._fit_mode = False

        new_scale = (
            self.transform().m11() * factor
        )

        new_scale = min(
            max(new_scale, 0.05),
            32.0
        )

        factor = (
            new_scale
            / self.transform().m11()
        )

        self.scale(factor, factor)
        self.zoom_changed.emit(
            self.zoom_percent()
        )