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
    QMenu,
)
from PySide6.QtGui import QKeyEvent

from ..constants import FrameType
from ...io.image_data import AstroImage



class FrameQTableWidget(QTableWidget):
    space_pressed = Signal()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Space:
            self.space_pressed.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            # クリックされた位置のセルインデックスを取得
            index = self.indexAt(event.position().toPoint())
            if index.isValid() and index.column() == 0:
                # 「使用」チェックボックスの列（第0列）がクリックされた場合
                item = self.item(index.row(), index.column())
                if item and (item.flags() & Qt.ItemFlag.ItemIsUserCheckable):
                    # 現在の複数選択状態を維持したまま、チェック状態だけを反転させる
                    current_state = item.checkState()
                    next_state = (
                        Qt.CheckState.Unchecked 
                        if current_state == Qt.CheckState.Checked 
                        else Qt.CheckState.Checked
                    )
                    item.setCheckState(next_state)
                    event.accept()
                    return # 通常のクリック処理（選択状態を1行に絞る挙動）をスキップ

        super().mousePressEvent(event)


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
    removed = Signal(object, object)
    selection_cleared = Signal(object)
    reference_image_requested = Signal(object)

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
        self._selected_rows = {ft: set() for ft in FrameType}
        self._bulk_updating = False
        self._current_reference_image: AstroImage | None = None

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

            table = FrameQTableWidget(0, len(self.HEADERS))
            table.setHorizontalHeaderLabels(self.HEADERS)
            table.setSortingEnabled(True)
            table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
            table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            table.itemChanged.connect(lambda item, ft=frame_type: self._on_item_changed(ft, item))
            page_layout.addWidget(table)

            table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            table.cellDoubleClicked.connect(lambda row, col, ft=frame_type: self._toggle_cell(ft, row, col))

            table.customContextMenuRequested.connect(lambda pos, ft=frame_type: self._show_menu(ft, pos))
            table.itemSelectionChanged.connect(lambda ft=frame_type: self._on_selection_changed(ft))
            table.space_pressed.connect(lambda ft=frame_type: self._toggle_selected_enabled(ft))
    
            select_all.clicked.connect(lambda checked=False, ft=frame_type: self._set_all(ft, True))
            clear_all.clicked.connect(lambda checked=False, ft=frame_type: self._set_all(ft, False))
            self._tables[frame_type] = table
            self.tabs.addTab(page, frame_type.display_name)

    def current_frame_type(self) -> FrameType:
        return list(FrameType)[self.tabs.currentIndex()]

    def set_frames(self, frame_map: dict[FrameType, list[AstroImage]], reference_image: AstroImage | None = None) -> None:
        self._frames = frame_map
        self._current_reference_image = reference_image
        for frame_type, frames in frame_map.items():
            self.show_frames(frame_type, frames, reference_image)

    def show_frames(self, frame_type: FrameType, frames: list[AstroImage], reference_image: AstroImage | None = None) -> None:
        if reference_image is None:
            reference_image = self._current_reference_image
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

            if reference_image is image:
                prefix = "⭐ "
            elif image.info.is_master:
                prefix = "★ "
            else:
                prefix = ""
            
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
            self.frame_selected.emit(None)
            return
        row_item = table.item(rows[0].row(), 0)
        source_row = row_item.data(Qt.ItemDataRole.UserRole)
        self.frame_selected.emit(self._frames[frame_type][source_row])

    def _on_item_changed(self, frame_type: FrameType, item: QTableWidgetItem):
        if self._bulk_updating: return
        if item.column() != 0: return

        table = self._tables[frame_type]
        checked = (item.checkState() == Qt.CheckState.Checked)
        
        # 現在選択されている行をそのまま取得（全操作で維持されるようになりました）
        selected_rows = {index.row() for index in table.selectionModel().selectedRows()}

        # 複数選択されていて、クリックされた（変更された）行がその選択内に含まれる場合
        if len(selected_rows) > 1 and item.row() in selected_rows:
            self._bulk_updating = True
            table.blockSignals(True) 

            for view_row in selected_rows:
                other = table.item(view_row, 0)
                if other is item or other is None:
                    continue
                other.setCheckState(item.checkState())

            table.blockSignals(False)
            self._bulk_updating = False

        # データモデル（AstroImage）への反映
        target_rows = selected_rows if (len(selected_rows) > 1 and item.row() in selected_rows) else {item.row()}
        
        for view_row in target_rows:
            enabled_item = table.item(view_row, 0)
            if enabled_item is None: continue
            
            source_row = enabled_item.data(Qt.ItemDataRole.UserRole)
            image = self._frames[frame_type][source_row]
            image.info.enabled = checked
            self.enabled_changed.emit(image, checked)


    def _set_all(self, frame_type: FrameType, enabled: bool) -> None:
        for image in self._frames[frame_type]:
            image.info.enabled = enabled
            
        self.show_frames(frame_type, self._frames[frame_type])

    def _selected_source_rows(self, frame_type: FrameType) -> list[int]:
        table = self._tables[frame_type]
        rows = []
        for index in table.selectionModel().selectedRows():
            item = table.item(index.row(), 0)
            rows.append(item.data(Qt.ItemDataRole.UserRole))
        return sorted(set(rows))

    def _selected_images(self, frame_type: FrameType) -> list[AstroImage]:
        rows = self._selected_source_rows(frame_type)
        return [self._frames[frame_type][row] for row in rows]

    def _set_selected_enabled(self, frame_type: FrameType, enabled: bool) -> None:
        table = self._tables[frame_type]
        for index in table.selectionModel().selectedRows():
            item = table.item(index.row(), 0)
            item.setCheckState(Qt.CheckState.Checked if enabled else Qt.CheckState.Unchecked)

    def _remove_selected(self, frame_type: FrameType) -> None:
        table = self._tables[frame_type]
        images = self._selected_images(frame_type)
        if not images:
            return

        table.clearSelection()
        self._selected_rows[frame_type].clear()
        self.frame_selected.emit(None)
        self.removed.emit(frame_type, images)

    def _show_menu(self, frame_type: FrameType, pos):
        table = self._tables[frame_type]
        menu = QMenu(self)

        selected_images = self._selected_images(frame_type)
        set_reference_action = None
        if len(selected_images) == 1:
            set_reference_action = menu.addAction("⭐ このフレームを基準画像に設定")
            menu.addSeparator()

        enable_action = menu.addAction("選択フレームを使用")
        disable_action = menu.addAction("選択フレームを無効化")
        menu.addSeparator()
        remove_action = menu.addAction("選択フレームを削除")

        action = menu.exec(table.viewport().mapToGlobal(pos))

        if action == set_reference_action and set_reference_action is not None:
            self.reference_image_requested.emit(selected_images[0])
        elif action == enable_action:
            self._set_selected_enabled(frame_type, True)
        elif action == disable_action:
            self._set_selected_enabled(frame_type, False)
        elif action == remove_action:
            self._remove_selected(frame_type)

    def keyPressEvent(self, event: QKeyEvent):
        frame_type = self.current_frame_type()

        if event.key() == Qt.Key.Key_Delete:
            self._remove_selected(frame_type)
            return

        if event.key() == Qt.Key.Key_Space:
            frame_type = self.current_frame_type()
            table = self._tables[frame_type]
            rows = table.selectionModel().selectedRows()
            if not rows:
                return

            item = table.item(rows[0].row(), 0)
            checked = (item.checkState() == Qt.CheckState.Checked)
            item.setCheckState(Qt.CheckState.Unchecked if checked else Qt.CheckState.Checked)
            event.accept()
            return

        super().keyPressEvent(event)

    def _toggle_cell(self, frame_type, row, col) -> None:
        if col != 0:
            return
        table = self._tables[frame_type]
        item = table.item(row, 0)
        checked = (item.checkState() == Qt.CheckState.Checked)
        item.setCheckState(Qt.CheckState.Unchecked if checked else Qt.CheckState.Checked)

    def _on_selection_changed(self, frame_type: FrameType):
        table = self._tables[frame_type]
        self._selected_rows[frame_type] = {
            index.row() for index in table.selectionModel().selectedRows()
        }
        self._emit_selected(frame_type)

    def _toggle_selected_enabled(self, frame_type: FrameType):
        table = self._tables[frame_type]
        rows = table.selectionModel().selectedRows()
        if not rows:
            return

        item = table.item(rows[0].row(), 0)
        checked = (item.checkState() == Qt.CheckState.Checked)
        item.setCheckState(Qt.CheckState.Unchecked if checked else Qt.CheckState.Checked)