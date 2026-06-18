from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QGraphicsPixmapItem, QGraphicsScene, QGraphicsView
import numpy as np


class ImageViewer(QGraphicsView):
    def __init__(self):
        super().__init__()
        self.scene = QGraphicsScene()
        self.setScene(self.scene)
        self.setBackgroundBrush(Qt.GlobalColor.black)
        self._pixmap_item: QGraphicsPixmapItem | None = None

    def set_image(self, image: np.ndarray | None) -> None:
        self.scene.clear()
        self._pixmap_item = None
        if image is None:
            return
        qimage = self._to_qimage(image)
        self._pixmap_item = self.scene.addPixmap(QPixmap.fromImage(qimage))
        self.scene.setSceneRect(self._pixmap_item.boundingRect())
        self.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._pixmap_item is not None:
            self.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def _to_qimage(self, image: np.ndarray) -> QImage:
        arr = np.squeeze(np.asarray(image, dtype=np.float32))
        finite = arr[np.isfinite(arr)]
        if finite.size == 0:
            arr = np.zeros_like(arr, dtype=np.float32)
        else:
            low, high = np.percentile(finite, (1, 99.5))
            arr = np.clip((arr - low) / (high - low + 1e-8), 0, 1)
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
