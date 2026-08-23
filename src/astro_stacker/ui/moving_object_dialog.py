from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QSettings, Qt, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from ..core.provider import ImageManagerProvider
from ..io.image_data import AstroImage
from ..io.image_manager import ImageManager
from ..moving_object.capture_time import capture_midpoint
from ..moving_object.models import MovingObjectAnchor
from ..platesolve import AstrometryNetSolver, PlateSolveSettings
from ..project.project import Project
from ..project.settings import ReferenceMode


def has_celestial_wcs(frame: AstroImage) -> bool:
    wcs = frame.info.wcs
    return (
        wcs is not None
        and callable(getattr(wcs, "world_to_pixel_values", None))
        and bool(getattr(wcs, "has_celestial", True))
    )


class _PlateSolveWorker(QObject):
    succeeded = Signal(object)
    failed = Signal(object)
    finished = Signal()

    def __init__(
        self,
        frame: AstroImage,
        manager: ImageManager,
        settings: PlateSolveSettings,
    ) -> None:
        super().__init__()
        self.frame = frame
        self.manager = manager
        self.settings = settings
        self.cancel_requested = False

    @Slot()
    def run(self) -> None:
        try:
            result = AstrometryNetSolver().solve(
                self.frame,
                ImageManagerProvider(self.manager),
                self.settings,
                is_cancelled=lambda: self.cancel_requested,
            )
            self.succeeded.emit(result)
        except Exception as exc:
            self.failed.emit(exc)
        finally:
            self.finished.emit()

    def cancel(self) -> None:
        self.cancel_requested = True


class MovingObjectSettingsDialog(QDialog):
    """Configure moving-object coordinate anchors and reference-frame WCS."""

    ANCHOR_COLUMN = 0
    FILE_COLUMN = 1
    TIME_COLUMN = 2
    RA_COLUMN = 3
    DEC_COLUMN = 4
    WCS_COLUMN = 5

    def __init__(self, project: Project, manager: ImageManager, parent=None) -> None:
        super().__init__(parent)
        self.project = project
        self.manager = manager
        self.frames = [frame for frame in project.light_frames if frame.info.enabled]
        self.app_settings = QSettings("AstroStacker", "AstroStacker")
        self._thread: QThread | None = None
        self._worker: _PlateSolveWorker | None = None
        self._solving_frame: AstroImage | None = None

        self.setWindowTitle("移動天体スタック設定")
        self.resize(900, 520)
        layout = QVBoxLayout(self)

        explanation = QLabel(
            "移動天体の赤経・赤緯を既知のフレーム（通常は先頭と末尾）に入力します。\n"
            "位置合わせ参照画像だけPlate Solveすれば、他フレームは恒星位置合わせ結果から座標変換します。"
        )
        explanation.setWordWrap(True)
        layout.addWidget(explanation)

        form = QFormLayout()
        self.alignment_reference = QComboBox()
        self.moving_reference = QComboBox()
        for frame in self.frames:
            value = str(frame.info.path)
            self.alignment_reference.addItem(frame.info.path.name, value)
            self.moving_reference.addItem(frame.info.path.name, value)
        form.addRow("位置合わせ参照画像", self.alignment_reference)
        form.addRow("移動天体の固定基準画像", self.moving_reference)

        self.executable = QLineEdit(
            self.app_settings.value("platesolve/executable", "solve-field", str)
        )
        self.downsample = QSpinBox()
        self.downsample.setRange(1, 8)
        self.downsample.setValue(self.app_settings.value("platesolve/downsample", 2, int))
        form.addRow("solve-field", self.executable)
        form.addRow("Downsample", self.downsample)
        layout.addLayout(form)

        self.table = QTableWidget(len(self.frames), 6)
        self.table.setHorizontalHeaderLabels(
            ["座標点", "ファイル", "露光中央時刻", "赤経 (deg)", "赤緯 (deg)", "WCS"]
        )
        self._populate_table()
        self.table.resizeColumnsToContents()
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        layout.addWidget(self.table)

        action_row = QHBoxLayout()
        self.solve_button = QPushButton("選択画像をPlate Solve")
        self.solve_button.clicked.connect(self._start_plate_solve)
        self.solve_status = QLabel("")
        action_row.addWidget(self.solve_button)
        action_row.addWidget(self.solve_status, 1)
        layout.addLayout(action_row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._select_initial_references()

    def _populate_table(self) -> None:
        existing = {
            anchor.frame_path: anchor
            for anchor in self.project.settings.moving_object.anchors
        }
        for row, frame in enumerate(self.frames):
            checkbox = QCheckBox()
            checkbox.setChecked(
                frame.info.path in existing
                or (not existing and row in {0, len(self.frames) - 1})
            )
            self.table.setCellWidget(row, self.ANCHOR_COLUMN, checkbox)

            name = QTableWidgetItem(frame.info.path.name)
            name.setFlags(name.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, self.FILE_COLUMN, name)

            midpoint = capture_midpoint(frame)
            time_item = QTableWidgetItem(midpoint.isoformat() if midpoint else f"撮影順 {row + 1}")
            time_item.setFlags(time_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, self.TIME_COLUMN, time_item)

            anchor = existing.get(frame.info.path)
            ra = QDoubleSpinBox()
            ra.setDecimals(8)
            ra.setRange(0.0, 360.0)
            ra.setValue(anchor.ra_deg if anchor else 0.0)
            dec = QDoubleSpinBox()
            dec.setDecimals(8)
            dec.setRange(-90.0, 90.0)
            dec.setValue(anchor.dec_deg if anchor else 0.0)
            self.table.setCellWidget(row, self.RA_COLUMN, ra)
            self.table.setCellWidget(row, self.DEC_COLUMN, dec)
            self._update_wcs_cell(row)

    def _select_initial_references(self) -> None:
        current = self.project.reference_image
        if current is None and self.frames:
            current = self.frames[len(self.frames) // 2]
        if current is not None:
            index = self.alignment_reference.findData(str(current.info.path))
            if index >= 0:
                self.alignment_reference.setCurrentIndex(index)

        moving_path = self.project.settings.moving_object.reference_frame_path
        if moving_path is None and current is not None:
            moving_path = current.info.path
        if moving_path is not None:
            index = self.moving_reference.findData(str(moving_path))
            if index >= 0:
                self.moving_reference.setCurrentIndex(index)

    def _frame_for_row(self, row: int) -> AstroImage | None:
        if 0 <= row < len(self.frames):
            return self.frames[row]
        return None

    def _selected_frame(self) -> AstroImage | None:
        rows = self.table.selectionModel().selectedRows()
        return self._frame_for_row(rows[0].row()) if rows else None

    def _update_wcs_cell(self, row: int) -> None:
        frame = self._frame_for_row(row)
        text = "Solved" if frame is not None and has_celestial_wcs(frame) else "未実行"
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.table.setItem(row, self.WCS_COLUMN, item)

    def _start_plate_solve(self) -> None:
        frame = self._selected_frame()
        if frame is None:
            QMessageBox.information(self, "Plate Solve", "先に画像の行を選択してください。")
            return

        settings = PlateSolveSettings(
            executable=self.executable.text().strip() or "solve-field",
            downsample=self.downsample.value(),
        )
        self.app_settings.setValue("platesolve/executable", settings.executable)
        self.app_settings.setValue("platesolve/downsample", settings.downsample)

        self.solve_button.setEnabled(False)
        self.solve_status.setText(f"実行中: {frame.info.path.name}")
        self._solving_frame = frame
        thread = QThread(self)
        worker = _PlateSolveWorker(frame, self.manager, settings)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.succeeded.connect(self._plate_solve_succeeded)
        worker.failed.connect(self._plate_solve_failed)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._plate_solve_finished)
        self._thread = thread
        self._worker = worker
        thread.start()

    @Slot(object)
    def _plate_solve_succeeded(self, result) -> None:
        if self._solving_frame is None:
            return
        self._solving_frame.info.wcs = result.wcs
        row = self.frames.index(self._solving_frame)
        self._update_wcs_cell(row)
        self.solve_status.setText(
            f"完了: 中心 RA {result.center_ra_deg:.6f}°, "
            f"Dec {result.center_dec_deg:.6f}°, {result.pixel_scale_arcsec:.3f} arcsec/pix"
        )

    @Slot(object)
    def _plate_solve_failed(self, exc: Exception) -> None:
        self.solve_status.setText("失敗")
        QMessageBox.critical(self, "Plate Solveエラー", str(exc))

    @Slot()
    def _plate_solve_finished(self) -> None:
        self.solve_button.setEnabled(True)
        self._thread = None
        self._worker = None
        self._solving_frame = None

    def _anchors(self) -> list[MovingObjectAnchor]:
        anchors: list[MovingObjectAnchor] = []
        for row, frame in enumerate(self.frames):
            checkbox = self.table.cellWidget(row, self.ANCHOR_COLUMN)
            if not isinstance(checkbox, QCheckBox) or not checkbox.isChecked():
                continue
            ra = self.table.cellWidget(row, self.RA_COLUMN)
            dec = self.table.cellWidget(row, self.DEC_COLUMN)
            if not isinstance(ra, QDoubleSpinBox) or not isinstance(dec, QDoubleSpinBox):
                continue
            anchors.append(MovingObjectAnchor(frame.info.path, ra.value(), dec.value()))
        return anchors

    def accept(self) -> None:
        if self._thread is not None:
            QMessageBox.information(self, "Plate Solve", "Plate Solveの完了を待ってください。")
            return
        anchors = self._anchors()
        if len(anchors) < 2:
            QMessageBox.warning(self, "移動天体座標", "座標点を2枚以上選択してください。")
            return
        reference_path = Path(self.alignment_reference.currentData())
        reference = next(frame for frame in self.frames if frame.info.path == reference_path)
        if not has_celestial_wcs(reference):
            QMessageBox.warning(
                self,
                "Plate Solveが必要です",
                "位置合わせ参照画像を選択してPlate Solveを実行してください。",
            )
            return

        self.project.set_reference_image(reference)
        self.project.settings.alignment.reference_mode = ReferenceMode.MANUAL
        moving = self.project.settings.moving_object
        moving.anchors = anchors
        moving.reference_frame_path = Path(self.moving_reference.currentData())
        super().accept()

    def reject(self) -> None:
        if self._worker is not None:
            self._worker.cancel()
            self.solve_status.setText("キャンセル中...")
            return
        super().reject()
