"""Reviewable polyline editor for wires and narrow obstructions."""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from ..masks.artifacts import detect_line_candidates, polyline_weight_mask
from .viewer.image_viewer import ImageViewer


class WireMaskViewer(ImageViewer):
    def __init__(self):
        super().__init__()
        self.polylines: list[list[QPointF]] = [[]]
        self.active_line = 0
        self._drag: tuple[int, int] | None = None
        self.display_width = 8.0
        self.setDragMode(self.DragMode.NoDrag)

    def set_polylines(self, polylines) -> None:
        self.polylines = [
            [QPointF(float(x), float(y)) for x, y in line]
            for line in polylines
            if len(line) >= 2
        ] or [[]]
        self.active_line = len(self.polylines) - 1
        self.viewport().update()

    def new_line(self) -> None:
        if self.polylines and not self.polylines[-1]:
            self.active_line = len(self.polylines) - 1
        else:
            self.polylines.append([])
            self.active_line = len(self.polylines) - 1
        self.viewport().update()

    def _nearest(self, point: QPointF) -> tuple[int, int] | None:
        scale = max(0.05, self.transform().m11())
        limit2 = (12.0 / scale) ** 2
        nearest = None
        nearest_distance = float("inf")
        for line_index, line in enumerate(self.polylines):
            for point_index, candidate in enumerate(line):
                distance = (candidate.x() - point.x()) ** 2 + (candidate.y() - point.y()) ** 2
                if distance < nearest_distance:
                    nearest = (line_index, point_index)
                    nearest_distance = distance
        return nearest if nearest_distance <= limit2 else None

    def mousePressEvent(self, event: QMouseEvent) -> None:
        point = self.mapToScene(event.position().toPoint())
        nearest = self._nearest(point)
        if event.button() == Qt.MouseButton.RightButton:
            if nearest is not None:
                line_index, point_index = nearest
                self.polylines[line_index].pop(point_index)
                self.polylines = [line for line in self.polylines if line] or [[]]
                self.active_line = min(self.active_line, len(self.polylines) - 1)
                self.viewport().update()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            if nearest is None:
                self.polylines[self.active_line].append(point)
                nearest = (self.active_line, len(self.polylines[self.active_line]) - 1)
            self._drag = nearest
            self.viewport().update()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag is not None:
            line_index, point_index = self._drag
            self.polylines[line_index][point_index] = self.mapToScene(event.position().toPoint())
            self.viewport().update()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag = None
        super().mouseReleaseEvent(event)

    def drawForeground(self, painter: QPainter, rect) -> None:
        super().drawForeground(painter, rect)
        painter.setPen(QPen(QColor(255, 80, 0, 210), self.display_width))
        for line in self.polylines:
            if len(line) >= 2:
                painter.drawPolyline(QPolygonF(line))
        painter.setPen(QPen(QColor(255, 255, 0), 2))
        for line in self.polylines:
            for point in line:
                painter.drawEllipse(point, 4, 4)


class WireMaskEditorDialog(QDialog):
    def __init__(self, image: np.ndarray, *, line_width=8.0, feather=3.0, parent=None):
        super().__init__(parent)
        self.image = np.asarray(image)
        self.setWindowTitle("電線・電柱・障害物マスク編集")
        self.resize(1000, 720)
        layout = QVBoxLayout(self)
        self.viewer = WireMaskViewer()
        self.viewer.set_image(self.image)
        layout.addWidget(self.viewer, 1)
        self.status = QLabel(
            "左クリック: 点追加・ドラッグ / 右クリック: 点削除。"
            "候補検出の結果は必ず確認してください。"
        )
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        controls = QHBoxLayout()
        new_line = QPushButton("新しい線")
        new_line.clicked.connect(self.viewer.new_line)
        detect = QPushButton("電線候補を検出")
        detect.clicked.connect(self._detect)
        clear = QPushButton("すべて消去")
        clear.clicked.connect(lambda: self.viewer.set_polylines([]))
        self.width = QDoubleSpinBox()
        self.width.setRange(1, 2000)
        self.width.setValue(line_width)
        self.width.setSuffix(" px 幅")
        self.width.valueChanged.connect(self._width_changed)
        self.feather = QDoubleSpinBox()
        self.feather.setRange(0, 100)
        self.feather.setValue(feather)
        self.feather.setSuffix(" px Feather")
        self.apply_to_all = QCheckBox("同じマスクを全Lightへ登録")
        self.apply_to_all.setToolTip(
            "固定撮影など、電線が全フレームの同じ画素位置にある場合だけ使用します。"
        )
        for widget in (
            new_line,
            detect,
            clear,
            self.width,
            self.feather,
            self.apply_to_all,
        ):
            controls.addWidget(widget)
        controls.addStretch()
        layout.addLayout(controls)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._width_changed(line_width)

    def _width_changed(self, value: float) -> None:
        self.viewer.display_width = value
        self.viewer.viewport().update()

    def _detect(self) -> None:
        try:
            candidates = detect_line_candidates(self.image)
        except ValueError as exc:
            self.status.setText(f"候補を検出できませんでした: {exc}")
            return
        self.viewer.set_polylines(candidates)
        self.status.setText(
            f"候補 {len(candidates)}本。誤検出は右クリックで点を削除し、必要な線を修正してください。"
        )

    def accept(self) -> None:
        if not any(len(line) >= 2 for line in self.viewer.polylines):
            self.status.setText("2点以上の線を1本以上指定してください。")
            return
        super().accept()

    def mask(self) -> np.ndarray:
        polylines = [
            [(point.x(), point.y()) for point in line]
            for line in self.viewer.polylines
            if len(line) >= 2
        ]
        return polyline_weight_mask(
            self.image.shape[:2],
            polylines,
            line_width=self.width.value(),
            feather=self.feather.value(),
        )
