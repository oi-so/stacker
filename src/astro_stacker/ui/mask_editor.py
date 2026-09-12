"""Interactive polygon editor for reviewable ground masks."""

import cv2
import numpy as np
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QBrush, QColor, QImage, QMouseEvent, QPen, QPolygonF
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from ..ground.mask import GroundMaskEstimate, estimate_ground_mask, polygon_sky_mask
from ..io.saver import save_fits
from .viewer.image_viewer import ImageViewer


class PolygonImageViewer(ImageViewer):
    """Left-click to add/drag, right-click to remove polygon vertices."""

    def __init__(self):
        super().__init__()
        self.points: list[QPointF] = []
        self._drag_index: int | None = None
        self.tool = "polygon"
        self.brush_size = 32.0
        self.painted_ground = np.zeros((1, 1), dtype=np.uint8)
        self._brush_cursor: QPointF | None = None
        self.setDragMode(self.DragMode.NoDrag)

    def set_image(self, image: np.ndarray) -> None:
        super().set_image(image)
        self.painted_ground = np.zeros(np.asarray(image).shape[:2], dtype=np.uint8)

    def set_tool(self, tool: str) -> None:
        self.tool = tool
        if tool not in {"paint", "erase"}:
            self._brush_cursor = None
        self.viewport().update()

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
        if self.tool in {"paint", "erase"} and event.button() == Qt.MouseButton.LeftButton:
            self._brush_cursor = point
            self._paint(point)
            self.viewport().update()
            return
        if self.tool != "polygon":
            return
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
        self._brush_cursor = self.mapToScene(event.position().toPoint())
        if self._drag_index is None and self.tool in {"paint", "erase"}:
            if event.buttons() & Qt.MouseButton.LeftButton:
                self._paint(self._brush_cursor)
            self.viewport().update()
            return
        if self._drag_index is not None:
            self.points[self._drag_index] = self.mapToScene(event.position().toPoint())
            self.viewport().update()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_index = None
        super().mouseReleaseEvent(event)

    def leaveEvent(self, event) -> None:
        self._brush_cursor = None
        self.viewport().update()
        super().leaveEvent(event)

    def _paint(self, point: QPointF) -> None:
        value = 255 if self.tool == "paint" else 0
        cv2.circle(
            self.painted_ground,
            (round(point.x()), round(point.y())),
            max(1, round(self.brush_size / 2)),
            value,
            -1,
            cv2.LINE_AA,
        )

    def drawForeground(self, painter, rect):
        super().drawForeground(painter, rect)
        if self.points:
            painter.setPen(QPen(QColor(0, 255, 255), 2))
            if len(self.points) >= 3:
                polygon = QPolygonF(self.points)
                painter.setBrush(QBrush(QColor(255, 80, 0, 70)))
                painter.drawPolygon(polygon)
            painter.setBrush(QBrush(QColor(255, 255, 0)))
            for point in self.points:
                painter.drawEllipse(point, 4, 4)
        if np.any(self.painted_ground):
            image = QImage(
                self.painted_ground.data,
                self.painted_ground.shape[1],
                self.painted_ground.shape[0],
                self.painted_ground.strides[0],
                QImage.Format.Format_Grayscale8,
            )
            painter.setOpacity(0.35)
            painter.drawImage(0, 0, image)
            painter.setOpacity(1.0)
        if self.tool in {"paint", "erase"} and self._brush_cursor is not None:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(255, 255, 255, 220), 2, Qt.PenStyle.DashLine))
            painter.drawEllipse(self._brush_cursor, self.brush_size / 2, self.brush_size / 2)


class GroundMaskEditorDialog(QDialog):
    def __init__(
        self,
        image: np.ndarray,
        estimate: GroundMaskEstimate | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.image = np.asarray(image)
        self.setWindowTitle("地上領域マスク編集")
        self.resize(1000, 720)
        layout = QVBoxLayout(self)
        self.viewer = PolygonImageViewer()
        self.viewer.set_image(self.image)
        layout.addWidget(self.viewer, 1)
        self.status = QLabel()
        layout.addWidget(self.status)
        controls = QHBoxLayout()
        self.tool = QPushButton("Polygonで地上領域")
        self.tool.setCheckable(True)
        self.tool.setChecked(True)
        self.tool.clicked.connect(lambda: self._set_tool("polygon"))
        paint = QPushButton("ペンで地上を塗る")
        erase = QPushButton("ペンで地上を消す")
        paint.clicked.connect(lambda: self._set_tool("paint"))
        erase.clicked.connect(lambda: self._set_tool("erase"))
        self.brush = QDoubleSpinBox()
        self.brush.setRange(2, 2000)
        self.brush.setValue(32)
        self.brush.setSuffix(" px ブラシ直径")
        self.brush.valueChanged.connect(lambda value: setattr(self.viewer, "brush_size", value))
        fit = QPushButton("Fit")
        fit.clicked.connect(self.viewer.fit_image)
        zoom_100 = QPushButton("100%")
        zoom_100.clicked.connect(lambda: self.viewer.set_zoom(100))
        zoom_out = QPushButton("-")
        zoom_out.clicked.connect(lambda: self.viewer.zoom_by_factor(0.8))
        zoom_in = QPushButton("+")
        zoom_in.clicked.connect(lambda: self.viewer.zoom_by_factor(1.25))
        fits = QPushButton("FITS保存")
        fits.clicked.connect(self._save_fits)
        retry = QPushButton("地上領域を自動推定")
        retry.clicked.connect(self._estimate)
        undo = QPushButton("1点戻す")
        undo.clicked.connect(self._undo)
        clear = QPushButton("Polygonを消去")
        clear.clicked.connect(lambda: self.viewer.set_points([]))
        self.feather = QDoubleSpinBox()
        self.feather.setRange(0, 256)
        self.feather.setValue(4)
        self.feather.setSuffix(" px Feather")
        controls.addWidget(self.tool)
        controls.addWidget(paint)
        controls.addWidget(erase)
        controls.addWidget(self.brush)
        controls.addWidget(fit)
        controls.addWidget(zoom_100)
        controls.addWidget(zoom_out)
        controls.addWidget(zoom_in)
        controls.addWidget(fits)
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

    def _set_tool(self, tool: str) -> None:
        self.viewer.set_tool(tool)
        self.tool.setChecked(tool == "polygon")

    def _save_fits(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "地上マスクをFITS保存", "ground_mask.fits", "FITS (*.fits)")
        if path:
            save_fits(self.mask(), path, frame_type="ground_mask")

    def _set_estimate(self, estimate: GroundMaskEstimate):
        h, w = estimate.sky_weight.shape
        sample_count = min(64, w)
        xs = np.linspace(0, w - 1, sample_count).round().astype(int)
        points = [(x, estimate.horizon_y[x]) for x in xs]
        points.extend([(w - 1, h - 1), (0, h - 1)])
        self.viewer.set_points(points)
        self.viewer.painted_ground.fill(0)
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
        if len(self.viewer.points) < 3 and not np.any(self.viewer.painted_ground):
            self.status.setText("Polygonには3点以上、またはペンで地上領域を塗ってください。")
            return
        super().accept()

    def mask(self) -> np.ndarray:
        points = [(point.x(), point.y()) for point in self.viewer.points]
        mask = polygon_sky_mask(self.image.shape[:2], points, self.feather.value())
        if np.any(self.viewer.painted_ground):
            mask[self.viewer.painted_ground > 0] = 0
        return mask
