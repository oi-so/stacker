"""Interactive polygon editor for reviewable ground masks."""

import numpy as np
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QBrush, QColor, QMouseEvent, QPen, QPolygonF
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from ..ground.mask import GroundMaskEstimate, estimate_ground_mask, polygon_sky_mask
from .viewer.image_viewer import ImageViewer


class PolygonImageViewer(ImageViewer):
    """Left-click to add/drag, right-click to remove polygon vertices."""

    def __init__(self):
        super().__init__()
        self.points: list[QPointF] = []
        self._drag_index: int | None = None
        self.setDragMode(self.DragMode.NoDrag)

    def set_points(self, points) -> None:
        self.points = [QPointF(float(x), float(y)) for x, y in points]
        self.viewport().update()

    def _nearest(self, point: QPointF) -> int | None:
        scale = max(0.05, self.transform().m11())
        limit2 = (12.0 / scale) ** 2
        distances = [
            (candidate.x() - point.x()) ** 2 + (candidate.y() - point.y()) ** 2
            for candidate in self.points
        ]
        if not distances:
            return None
        index = int(np.argmin(distances))
        return index if distances[index] <= limit2 else None

    def mousePressEvent(self, event: QMouseEvent) -> None:
        point = self.mapToScene(event.position().toPoint())
        if event.button() == Qt.MouseButton.RightButton:
            index = self._nearest(point)
            if index is not None:
                self.points.pop(index)
                self.viewport().update()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_index = self._nearest(point)
            if self._drag_index is None:
                self.points.append(point)
                self._drag_index = len(self.points) - 1
            self.viewport().update()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_index is not None:
            self.points[self._drag_index] = self.mapToScene(event.position().toPoint())
            self.viewport().update()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_index = None
        super().mouseReleaseEvent(event)

    def drawForeground(self, painter, rect):
        super().drawForeground(painter, rect)
        if not self.points:
            return
        painter.setPen(QPen(QColor(0, 255, 255), 2))
        if len(self.points) >= 3:
            polygon = QPolygonF(self.points)
            painter.setBrush(QBrush(QColor(255, 80, 0, 70)))
            painter.drawPolygon(polygon)
        painter.setBrush(QBrush(QColor(255, 255, 0)))
        for point in self.points:
            painter.drawEllipse(point, 4, 4)


class GroundMaskEditorDialog(QDialog):
    def __init__(
        self,
        image: np.ndarray,
        estimate: GroundMaskEstimate | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.image = np.asarray(image)
        self.setWindowTitle("地上マスク Polygon編集")
        self.resize(1000, 720)
        layout = QVBoxLayout(self)
        self.viewer = PolygonImageViewer()
        self.viewer.set_image(self.image)
        layout.addWidget(self.viewer, 1)
        self.status = QLabel()
        layout.addWidget(self.status)
        controls = QHBoxLayout()
        retry = QPushButton("自動推定をやり直す")
        retry.clicked.connect(self._estimate)
        undo = QPushButton("1点戻す")
        undo.clicked.connect(self._undo)
        clear = QPushButton("Polygonを消去")
        clear.clicked.connect(lambda: self.viewer.set_points([]))
        self.feather = QDoubleSpinBox()
        self.feather.setRange(0, 256)
        self.feather.setValue(4)
        self.feather.setSuffix(" px Feather")
        controls.addWidget(retry)
        controls.addWidget(undo)
        controls.addWidget(clear)
        controls.addWidget(self.feather)
        controls.addStretch()
        layout.addLayout(controls)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._set_estimate(estimate or estimate_ground_mask(self.image))

    def _set_estimate(self, estimate: GroundMaskEstimate):
        h, w = estimate.sky_weight.shape
        sample_count = min(64, w)
        xs = np.linspace(0, w - 1, sample_count).round().astype(int)
        points = [(x, estimate.horizon_y[x]) for x in xs]
        points.extend([(w - 1, h - 1), (0, h - 1)])
        self.viewer.set_points(points)
        warning = f" / {estimate.warning}" if estimate.warning else ""
        self.status.setText(
            f"推定信頼度: {estimate.confidence:.0%}{warning}  "
            "左クリック: 点追加・ドラッグ / 右クリック: 点削除"
        )

    def _estimate(self):
        self._set_estimate(estimate_ground_mask(self.image, self.feather.value()))

    def _undo(self):
        if self.viewer.points:
            self.viewer.points.pop()
            self.viewer.viewport().update()

    def accept(self):
        if len(self.viewer.points) < 3:
            self.status.setText("Polygonには3点以上必要です。")
            return
        super().accept()

    def mask(self) -> np.ndarray:
        points = [(point.x(), point.y()) for point in self.viewer.points]
        return polygon_sky_mask(self.image.shape[:2], points, self.feather.value())
