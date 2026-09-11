"""Reviewable line/polygon editor for frame-local obstructions."""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import QObject, QPointF, Qt, QThread, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from ..masks.artifacts import (
    detect_line_candidates,
    polygon_weight_mask,
    polyline_weight_mask,
)
from .viewer.image_viewer import ImageViewer


class WireMaskViewer(ImageViewer):
    def __init__(self):
        super().__init__()
        self.polylines: list[list[QPointF]] = [[]]
        self.closed: list[bool] = [False]
        self.active_line = 0
        self._drag: tuple[int, int] | None = None
        self.display_width = 8.0
        self.setDragMode(self.DragMode.NoDrag)

    def set_polylines(self, polylines, *, closed: bool = False) -> None:
        self.polylines = [
            [QPointF(float(x), float(y)) for x, y in line]
            for line in polylines
            if len(line) >= 2
        ] or [[]]
        self.closed = [closed] * len(self.polylines)
        self.active_line = len(self.polylines) - 1
        self.viewport().update()

    def new_line(self) -> None:
        self.new_shape(closed=False)

    def new_area(self) -> None:
        self.new_shape(closed=True)

    def new_shape(self, *, closed: bool) -> None:
        if self.polylines and not self.polylines[-1]:
            self.active_line = len(self.polylines) - 1
            self.closed[self.active_line] = closed
        else:
            self.polylines.append([])
            self.closed.append(closed)
            self.active_line = len(self.polylines) - 1
        self.viewport().update()

    def clear_shapes(self) -> None:
        self.polylines = [[]]
        self.closed = [False]
        self.active_line = 0
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
                retained = [
                    (line, closed)
                    for line, closed in zip(self.polylines, self.closed, strict=True)
                    if line
                ]
                if retained:
                    self.polylines = [line for line, _ in retained]
                    self.closed = [closed for _, closed in retained]
                else:
                    self.polylines = [[]]
                    self.closed = [False]
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
        for line, closed in zip(self.polylines, self.closed, strict=True):
            if closed and len(line) >= 3:
                painter.drawPolygon(QPolygonF(line))
            elif len(line) >= 2:
                painter.drawPolyline(QPolygonF(line))
        painter.setPen(QPen(QColor(255, 255, 0), 2))
        for line in self.polylines:
            for point in line:
                painter.drawEllipse(point, 4, 4)


class LineDetectionWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, image: np.ndarray):
        super().__init__()
        self.image = image

    def run(self) -> None:
        try:
            self.finished.emit(detect_line_candidates(self.image))
        except Exception as exc:
            self.failed.emit(str(exc))


class WireMaskEditorDialog(QDialog):
    def __init__(
        self,
        image: np.ndarray,
        *,
        line_width=8.0,
        feather=3.0,
        allow_apply_to_all: bool = True,
        parent=None,
    ):
        super().__init__(parent)
        self.image = np.asarray(image)
        self._detect_thread: QThread | None = None
        self._detect_worker: LineDetectionWorker | None = None
        self.setWindowTitle("電線・電柱・障害物マスク編集")
        self.resize(1000, 720)
        layout = QVBoxLayout(self)
        self.viewer = WireMaskViewer()
        self.viewer.set_image(self.image)
        layout.addWidget(self.viewer, 1)
        self.status = QLabel(
            "電線は一本ごとに「新しい線」、電柱や面状障害物は「新しい面」を選びます。"
            "左クリック: 点追加・ドラッグ / 右クリック: 点削除。"
        )
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        controls = QHBoxLayout()
        new_line = QPushButton("新しい線")
        new_line.clicked.connect(self.viewer.new_line)
        new_area = QPushButton("新しい面")
        new_area.clicked.connect(self.viewer.new_area)
        self.detect_button = QPushButton("電線候補を検出")
        self.detect_button.clicked.connect(self._detect)
        clear = QPushButton("すべて消去")
        clear.clicked.connect(self.viewer.clear_shapes)
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
        if not allow_apply_to_all:
            self.apply_to_all.setEnabled(False)
            self.apply_to_all.setToolTip(
                "追尾・位置合わせ撮影では障害物がフレームごとに移動するため使用できません。"
                "各Lightを選んで個別にマスクを登録してください。"
            )
            self.status.setText(
                "追尾・位置合わせ撮影です。障害物はフレームごとに位置が変わるため、"
                "このLightだけにマスクを登録します。新しく現れた障害物も該当Lightで追加してください。"
            )
        for widget in (
            new_line,
            new_area,
            self.detect_button,
            clear,
            self.width,
            self.feather,
            self.apply_to_all,
        ):
            controls.addWidget(widget)
        controls.addStretch()
        layout.addLayout(controls)
        self.detection_progress = QProgressBar()
        self.detection_progress.setVisible(False)
        layout.addWidget(self.detection_progress)

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
        if self._detect_thread is not None:
            return
        self.status.setText("電線候補を解析しています…")
        self.detection_progress.setRange(0, 0)
        self.detection_progress.setVisible(True)
        self.detect_button.setEnabled(False)
        thread = QThread(self)
        worker = LineDetectionWorker(self.image)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._detection_finished)
        worker.failed.connect(self._detection_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._detection_thread_finished)
        self._detect_thread = thread
        self._detect_worker = worker
        thread.start()

    def _detection_finished(self, candidates) -> None:
        self.viewer.set_polylines(candidates)
        self.status.setText(
            f"候補 {len(candidates)}本。誤検出は右クリックで点を削除し、必要な線を修正してください。"
        )

    def _detection_failed(self, message: str) -> None:
        self.status.setText(f"候補を検出できませんでした: {message}")

    def _detection_thread_finished(self) -> None:
        self.detection_progress.setRange(0, 1)
        self.detection_progress.setValue(0)
        self.detection_progress.setVisible(False)
        self.detect_button.setEnabled(True)
        self._detect_thread = None
        self._detect_worker = None

    def reject(self) -> None:
        if self._detect_thread is not None:
            self.status.setText("候補解析が終わるまでお待ちください。")
            return
        super().reject()

    def accept(self) -> None:
        if self._detect_thread is not None:
            self.status.setText("候補解析が終わるまでお待ちください。")
            return
        valid = any(
            len(line) >= (3 if closed else 2)
            for line, closed in zip(
                self.viewer.polylines, self.viewer.closed, strict=True
            )
        )
        if not valid:
            self.status.setText("線は2点以上、面は3点以上指定してください。")
            return
        super().accept()

    def mask(self) -> np.ndarray:
        polylines = [
            [(point.x(), point.y()) for point in line]
            for line, closed in zip(
                self.viewer.polylines, self.viewer.closed, strict=True
            )
            if not closed and len(line) >= 2
        ]
        polygons = [
            [(point.x(), point.y()) for point in line]
            for line, closed in zip(
                self.viewer.polylines, self.viewer.closed, strict=True
            )
            if closed and len(line) >= 3
        ]
        line_mask = polyline_weight_mask(
            self.image.shape[:2],
            polylines,
            line_width=self.width.value(),
            feather=self.feather.value(),
        )
        area_mask = polygon_weight_mask(
            self.image.shape[:2], polygons, feather=self.feather.value()
        )
        return np.multiply(line_mask, area_mask, dtype=np.float32)
