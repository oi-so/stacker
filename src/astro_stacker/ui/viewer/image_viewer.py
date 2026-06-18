from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QMouseEvent, QPixmap, QPainter
from PySide6.QtWidgets import QGraphicsPixmapItem, QGraphicsScene, QGraphicsView
import numpy as np


class ImageViewer(QGraphicsView):
    def __init__(self):
        super().__init__()
        self.scene = QGraphicsScene()
        self.setScene(self.scene)
        self.setBackgroundBrush(Qt.GlobalColor.black)
        self._pixmap_item: QGraphicsPixmapItem | None = None
        self.setRenderHint(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        self._pixmap_item = None

         # ドラッグで移動
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)

        # アンカーをマウス位置へ
        self.setTransformationAnchor(
            QGraphicsView.ViewportAnchor.AnchorUnderMouse
        )
        self.setResizeAnchor(
            QGraphicsView.ViewportAnchor.AnchorUnderMouse
        )

        self._zoom = 0

    
    def fit_image(self):
        if self._pixmap_item is None:
            return

        self.fitInView(
            self.scene.sceneRect(),
            Qt.AspectRatioMode.KeepAspectRatio
        )

        self._zoom = 0

    def set_image(self, image: np.ndarray | None) -> None:
        self.scene.clear()
        self._pixmap_item = None
        if image is None:
            return
        qimage = self._to_qimage(image)
        self._pixmap_item = self.scene.addPixmap(QPixmap.fromImage(qimage))
        self.scene.setSceneRect(self._pixmap_item.boundingRect())
        self.fit_image()

    def resizeEvent(self, event):
        super().resizeEvent(event)

        if self._pixmap_item is None:
            return

        # 全体表示中だけ再Fit
        if self._zoom == 0:
            self.fit_image()

    
    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        self.fit_image()
        super().mouseDoubleClickEvent(event)


    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_0:
            self.fit_image()
        elif event.key() == Qt.Key.Key_1:
            self.resetTransform()
            self._zoom = 1

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

        factor = 1.25

        if event.angleDelta().y() > 0:
            scale = factor
            self._zoom += 1
        else:
            scale = 1 / factor
            self._zoom -= 1

        # 縮小しすぎ防止
        if self._zoom < -5:
            self._zoom = -5
            return

        # 拡大しすぎ防止
        if self._zoom > 30:
            self._zoom = 30
            return

        self.scale(scale, scale)
