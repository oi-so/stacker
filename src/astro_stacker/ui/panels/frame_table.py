from __future__ import annotations

from pathlib import Path
from fractions import Fraction

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..constants import FrameType
from ...io.image_data import AstroImage


class NumericItem(QTableWidgetItem):
    def __lt__(self, other):
        left = self.data(Qt.ItemDataRole.UserRole)
        right = other.data(Qt.ItemDataRole.UserRole)
        if left is not None and right is not None:
            return left < right
        return super().__lt__(other)


class FrameTable(QWidget):
    frame_selected = Signal(object)
    files_dropped = Signal(object, object)
    enabled_changed = Signal(object, bool)

    HEADERS = ["使用", "ファイル名", "日時", "ISO", "SS", "F値", "スコア"]

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self._frames: dict[FrameType, list[AstroImage]] = {frame_type: [] for frame_type in FrameType}
        self._tables: dict[FrameType, QTableWidget] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        for frame_type in FrameType:
            page = QWidget()
            page_layout = QVBoxLayout(page)
            buttons = QHBoxLayout()
            select_all = QPushButton("全選択")
            clear_all = QPushButton("全解除")
            buttons.addWidget(select_all)
            buttons.addWidget(clear_all)
            buttons.addStretch()
            page_layout.addLayout(buttons)

            table = QTableWidget(0, len(self.HEADERS))
            table.setHorizontalHeaderLabels(self.HEADERS)
            table.setSortingEnabled(True)
            table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            table.itemSelectionChanged.connect(lambda ft=frame_type: self._emit_selected(ft))
            table.itemChanged.connect(lambda item, ft=frame_type: self._on_item_changed(ft, item))
            page_layout.addWidget(table)

            select_all.clicked.connect(lambda checked=False, ft=frame_type: self._set_all(ft, True))
            clear_all.clicked.connect(lambda checked=False, ft=frame_type: self._set_all(ft, False))
            self._tables[frame_type] = table
            self.tabs.addTab(page, frame_type.display_name)

    def current_frame_type(self) -> FrameType:
        return list(FrameType)[self.tabs.currentIndex()]

    def set_frames(self, frame_map: dict[FrameType, list[AstroImage]]) -> None:
        self._frames = frame_map
        for frame_type, frames in frame_map.items():
            self.show_frames(frame_type, frames)

    def show_frames(self, frame_type: FrameType, frames: list[AstroImage]) -> None:
        self._frames[frame_type] = frames
        table = self._tables[frame_type]
        table.blockSignals(True)
        table.setSortingEnabled(False)
        table.setRowCount(len(frames))
        for row, image in enumerate(frames):
            enabled = QTableWidgetItem()
            enabled.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            enabled.setCheckState(Qt.CheckState.Checked if image.info.enabled else Qt.CheckState.Unchecked)
            enabled.setData(Qt.ItemDataRole.UserRole, row)
            table.setItem(row, 0, enabled)

            prefix = "★ " if image.info.is_master else ""
            table.setItem(row, 1, QTableWidgetItem(prefix + image.info.path.name))
            table.setItem(row, 2, self._item(self._datetime(image), self._datetime(image)))
            table.setItem(row, 3, self._item(str(image.info.iso) if image.info.iso else "—", image.info.iso))
            table.setItem(row, 4, self._item(self._exposure(image), image.info.exposure_time))
            table.setItem(row, 5, self._item(f"F{image.info.f_number:g}" if image.info.f_number else "—", image.info.f_number))
            score = image.info.score_data.score
            table.setItem(row, 6, self._item(f"{score:.2f}" if score is not None else "—", score))
        table.setSortingEnabled(True)
        table.resizeColumnsToContents()
        table.blockSignals(False)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
        if paths:
            self.files_dropped.emit(self.current_frame_type(), paths)

    def _item(self, text: str, sort_value=None) -> QTableWidgetItem:
        item = NumericItem(text)
        item.setData(Qt.ItemDataRole.UserRole, sort_value)
        return item

    def _datetime(self, image: AstroImage) -> str:
        exif = image.info.exif or {}
        return str(exif.get("EXIF DateTimeOriginal") or exif.get("DATE-OBS") or "—")

    def _exposure(self, image: AstroImage) -> str:
        value = image.info.exposure_time
        if value is None:
            return "—"
        if value < 1:
            return str(Fraction(value).limit_denominator(8000))
        return f"{value:g}s"

    def _emit_selected(self, frame_type: FrameType) -> None:
        table = self._tables[frame_type]
        rows = table.selectionModel().selectedRows()
        if not rows:
            return
        row_item = table.item(rows[0].row(), 0)
        source_row = row_item.data(Qt.ItemDataRole.UserRole)
        self.frame_selected.emit(self._frames[frame_type][source_row])

    def _on_item_changed(self, frame_type: FrameType, item: QTableWidgetItem) -> None:
        if item.column() != 0:
            return
        row = item.data(Qt.ItemDataRole.UserRole)
        image = self._frames[frame_type][row]
        image.info.enabled = item.checkState() == Qt.CheckState.Checked
        self.enabled_changed.emit(image, image.info.enabled)

    def _set_all(self, frame_type: FrameType, enabled: bool) -> None:
        for image in self._frames[frame_type]:
            image.info.enabled = enabled
        self.show_frames(frame_type, self._frames[frame_type])
