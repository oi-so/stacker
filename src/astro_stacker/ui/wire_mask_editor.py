"""Reviewable line/polygon editor for frame-local obstructions."""

from __future__ import annotations

import cv2
import numpy as np
from PySide6.QtCore import QObject, QPointF, Qt, QThread, Signal
from PySide6.QtGui import QColor, QImage, QMouseEvent, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from ..io.saver import save_fits
from ..masks.artifacts import (
    detect_line_candidates,
    painted_obstruction_weight_mask,
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
        self.tool = "shape"
        self.brush_size = 24.0
        self.painted = np.zeros((1, 1), dtype=np.uint8)
        self._paint_history: list[np.ndarray] = []
        self._paint_redo: list[np.ndarray] = []
        self._brush_cursor: QPointF | None = None
        self.setDragMode(self.DragMode.NoDrag)

    def set_image(self, image: np.ndarray) -> None:
        super().set_image(image)
        self.painted = np.zeros(np.asarray(image).shape[:2], dtype=np.uint8)
        self._paint_history.clear()
        self._paint_redo.clear()

    def set_tool(self, tool: str) -> None:
        self.tool = tool
        if tool not in {"paint", "erase"}:
            self._brush_cursor = None
        self.viewport().update()

    def undo_paint(self) -> None:
        if self._paint_history:
            self._paint_redo.append(self.painted.copy())
            self.painted = self._paint_history.pop()
            self.viewport().update()

    def redo_paint(self) -> None:
        if self._paint_redo:
            self._paint_history.append(self.painted.copy())
            self.painted = self._paint_redo.pop()
            self.viewport().update()

    def _paint(self, point: QPointF, *, erase: bool) -> None:
        value = 0 if erase else 255
        cv2.circle(
            self.painted, (round(point.x()), round(point.y())),
            max(1, round(self.brush_size / 2)), value, -1, cv2.LINE_AA,
        )

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
        self._paint_history.append(self.painted.copy())
        self._paint_redo.clear()
        self.painted.fill(0)
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
        if self.tool in {"paint", "erase"} and event.button() == Qt.MouseButton.LeftButton:
            self._brush_cursor = point
            self._paint_history.append(self.painted.copy())
            self._paint_redo.clear()
            self._paint(point, erase=self.tool == "erase")
            self._drag = (-1, -1)
            self.viewport().update()
            return
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
        self._brush_cursor = self.mapToScene(event.position().toPoint())
        if self._drag == (-1, -1):
            self._paint(self._brush_cursor, erase=self.tool == "erase")
            self.viewport().update()
            return
        if self._drag is not None:
            line_index, point_index = self._drag
            self.polylines[line_index][point_index] = self.mapToScene(event.position().toPoint())
            self.viewport().update()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag = None
        super().mouseReleaseEvent(event)

    def leaveEvent(self, event) -> None:
        self._brush_cursor = None
        self.viewport().update()
        super().leaveEvent(event)

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
        if np.any(self.painted):
            image = QImage(
                self.painted.data, self.painted.shape[1], self.painted.shape[0],
                self.painted.strides[0], QImage.Format.Format_Grayscale8,
            )
            painter.setOpacity(0.35)
            painter.drawImage(0, 0, image)
            painter.setOpacity(1.0)
        if self.tool in {"paint", "erase"} and self._brush_cursor is not None:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(255, 255, 255, 220), 2, Qt.PenStyle.DashLine))
            painter.drawEllipse(
                self._brush_cursor,
                self.brush_size / 2,
                self.brush_size / 2,
            )


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
            "ブラシでは不規則な枝・建物・写り込みも直接塗れます。"
            "形状編集は左クリック: 点追加・ドラッグ / 右クリック: 点削除。"
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
        self.tool = QComboBox()
        self.tool.addItem("線・面を編集", "shape")
        self.tool.addItem("ブラシで障害物を塗る", "paint")
        self.tool.addItem("ブラシで塗りを消す", "erase")
        self.tool.currentIndexChanged.connect(self._update_tool_widgets)
        self.brush = QDoubleSpinBox()
        self.brush.setRange(2, 2000)
        self.brush.setValue(24)
        self.brush.setSuffix(" px ブラシ直径")
        self.brush.setToolTip(
            "ブラシで塗る範囲の直径です。カーソル位置に円で表示されます。"
        )
        self.brush.valueChanged.connect(lambda value: setattr(self.viewer, "brush_size", value))
        self.undo_paint_button = QPushButton("ブラシ Undo")
        self.undo_paint_button.clicked.connect(self.viewer.undo_paint)
        self.redo_paint_button = QPushButton("ブラシ Redo")
        self.redo_paint_button.clicked.connect(self.viewer.redo_paint)
        clear = QPushButton("すべて消去")
        clear.clicked.connect(self.viewer.clear_shapes)
        self.width = QDoubleSpinBox()
        self.width.setRange(1, 2000)
        self.width.setValue(line_width)
        self.width.setSuffix(" px 線幅")
        self.width.setToolTip(
            "線・面ツールで作成する形状の太さです。ブラシの大きさとは別に設定します。"
        )
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
        for widget in (
            new_line,
            new_area,
            self.detect_button,
            self.tool,
            self.brush,
            self.undo_paint_button,
            self.redo_paint_button,
            clear,
            self.width,
            self.feather,
            self.apply_to_all,
            fit,
            zoom_100,
            zoom_out,
            zoom_in,
            fits,
        ):
            controls.addWidget(widget)
        controls.addStretch()
        layout.addLayout(controls)
        self.detection_progress = QProgressBar()
        self.detection_progress.setVisible(False)
        layout.addWidget(self.detection_progress)
        self._update_tool_widgets()

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

    def _save_fits(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "障害物マスクをFITS保存", "artifact_mask.fits", "FITS (*.fits)"
        )
        if path:
            save_fits(self.mask(), path, frame_type="artifact_mask")

    def _update_tool_widgets(self) -> None:
        tool = self.tool.currentData()
        brush_mode = tool in {"paint", "erase"}
        self.viewer.set_tool(tool)
        self.brush.setEnabled(brush_mode)
        self.undo_paint_button.setEnabled(brush_mode)
        self.redo_paint_button.setEnabled(brush_mode)
        self.width.setEnabled(not brush_mode)

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
        valid = np.any(self.viewer.painted) or any(
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
        paint_mask = painted_obstruction_weight_mask(
            self.viewer.painted, feather=self.feather.value()
        )
        return np.multiply(np.multiply(line_mask, area_mask), paint_mask, dtype=np.float32)
