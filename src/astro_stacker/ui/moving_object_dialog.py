from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from PySide6.QtCore import QDateTime, QObject, QSettings, Qt, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateTimeEdit,
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
from ..moving_object.capture_time import (
    apply_corrected_capture_starts,
    capture_midpoint,
    corrected_capture_starts,
)
from ..moving_object.catalog import SmallBodyCatalog
from ..moving_object.ephemeris import HorizonsEphemeris
from ..moving_object.models import CatalogObject, MovingObjectAnchor, MovingObjectMode
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


class _NetworkWorker(QObject):
    succeeded = Signal(object)
    failed = Signal(object)
    finished = Signal()

    def __init__(self, operation) -> None:
        super().__init__()
        self.operation = operation

    @Slot()
    def run(self) -> None:
        try:
            self.succeeded.emit(self.operation())
        except Exception as exc:
            self.failed.emit(exc)
        finally:
            self.finished.emit()


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
        self._worker: QObject | None = None
        self._solving_frame: AstroImage | None = None
        self._corrected_starts: dict[Path, datetime] = {}
        self._catalog_results: list[CatalogObject] = []
        self._ephemeris_ready = False

        self.setWindowTitle("移動天体スタック設定")
        self.resize(1000, 760)
        layout = QVBoxLayout(self)

        explanation = QLabel(
            "手入力した赤経・赤緯、またはJPLカタログの彗星・小惑星から"
            "位置を設定します。\n"
            "撮影時刻 → 軌道計算 → 基準画像1枚のPlate Solve → "
            "恒星位置から全画像へ伝播、の順に実行します。"
        )
        explanation.setWordWrap(True)
        layout.addWidget(explanation)

        form = QFormLayout()
        self.mode = QComboBox()
        self.mode.addItem("赤経・赤緯を手入力", MovingObjectMode.MANUAL)
        self.mode.addItem("JPLカタログから選択", MovingObjectMode.CATALOG)
        current_mode = self.project.settings.moving_object.mode
        self.mode.setCurrentIndex(max(0, self.mode.findData(current_mode)))
        form.addRow("設定方法", self.mode)

        first_midpoint = capture_midpoint(self.frames[0]) if self.frames else None
        first_exposure = float(self.frames[0].info.exposure_time or 0.0) if self.frames else 0.0
        first_start = (
            first_midpoint - timedelta(seconds=first_exposure / 2.0)
            if first_midpoint
            else datetime.now(UTC)
        )
        self.first_time = QDateTimeEdit()
        self.first_time.setDisplayFormat("yyyy-MM-dd HH:mm:ss.zzz 'UTC'")
        self.first_time.setTimeSpec(Qt.TimeSpec.UTC)
        qt_first_start = QDateTime.fromString(
            first_start.isoformat(), Qt.DateFormat.ISODate
        ).toUTC()
        self.first_time.setDateTime(qt_first_start)
        self.frame_interval = QDoubleSpinBox()
        self.frame_interval.setRange(0.001, 86400.0)
        self.frame_interval.setDecimals(3)
        self.frame_interval.setSuffix(" 秒")
        self.frame_interval.setValue(self._estimated_interval())
        time_row = QHBoxLayout()
        time_row.addWidget(self.first_time, 1)
        time_row.addWidget(QLabel("不足時の間隔"))
        time_row.addWidget(self.frame_interval)
        self.apply_time_button = QPushButton("全画像へ反映")
        self.apply_time_button.clicked.connect(self._apply_time_correction)
        time_row.addWidget(self.apply_time_button)
        form.addRow("先頭画像の撮影開始", time_row)

        self.catalog_query = QLineEdit()
        self.catalog_query.setPlaceholderText("例: 12P, C/2023 A3, Eros, 433")
        self.catalog_search_button = QPushButton("検索")
        self.catalog_search_button.clicked.connect(self._search_catalog)
        search_row = QHBoxLayout()
        search_row.addWidget(self.catalog_query, 1)
        search_row.addWidget(self.catalog_search_button)
        form.addRow("彗星・小惑星を検索", search_row)
        self.catalog_results = QComboBox()
        form.addRow("検索結果", self.catalog_results)
        self.observer_code = QLineEdit(self.project.settings.moving_object.observer_code)
        self.observer_code.setToolTip("JPL Horizons観測地点コード。500は地心です。")
        form.addRow("観測地点コード", self.observer_code)
        self.ephemeris_button = QPushButton("選択天体の軌道位置を計算")
        self.ephemeris_button.clicked.connect(self._calculate_ephemeris)
        form.addRow("軌道計算", self.ephemeris_button)
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
        self.solve_button = QPushButton("基準画像をPlate Solve（推奨設定）")
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
        self.mode.currentIndexChanged.connect(self._update_mode_widgets)
        self._restore_catalog_object()
        self._apply_time_correction()
        self._ephemeris_ready = (
            current_mode == MovingObjectMode.CATALOG
            and len(self.project.settings.moving_object.anchors) == len(self.frames)
        )
        self.first_time.dateTimeChanged.connect(self._invalidate_ephemeris)
        self.frame_interval.valueChanged.connect(self._invalidate_ephemeris)
        self.catalog_results.currentIndexChanged.connect(self._invalidate_ephemeris)
        self._update_mode_widgets()

    def _invalidate_ephemeris(self, *_args) -> None:
        self._ephemeris_ready = False

    def _estimated_interval(self) -> float:
        values = [capture_midpoint(frame) for frame in self.frames]
        intervals = [
            (end - start).total_seconds()
            for start, end in zip(values, values[1:])
            if start is not None and end is not None and end > start
        ]
        if intervals:
            return max(0.001, sorted(intervals)[len(intervals) // 2])
        exposure = float(self.frames[0].info.exposure_time or 1.0) if self.frames else 1.0
        return max(0.001, exposure)

    def _apply_time_correction(self) -> None:
        value = self.first_time.dateTime().toUTC().toPython()
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        self._corrected_starts = corrected_capture_starts(
            self.frames, value, self.frame_interval.value()
        )
        for row, frame in enumerate(self.frames):
            start = self._corrected_starts[frame.info.path]
            midpoint = start + timedelta(seconds=float(frame.info.exposure_time or 0.0) / 2.0)
            self.table.item(row, self.TIME_COLUMN).setText(midpoint.isoformat())

    def _restore_catalog_object(self) -> None:
        selected = self.project.settings.moving_object.catalog_object
        if selected is None:
            return
        self._catalog_results = [selected]
        self.catalog_results.addItem(selected.fullname, selected)
        self.catalog_query.setText(selected.designation)

    def _update_mode_widgets(self) -> None:
        catalog = self.mode.currentData() == MovingObjectMode.CATALOG
        for widget in (
            self.catalog_query,
            self.catalog_search_button,
            self.catalog_results,
            self.observer_code,
            self.ephemeris_button,
        ):
            widget.setEnabled(catalog)
        for row in range(self.table.rowCount()):
            for column in (self.ANCHOR_COLUMN, self.RA_COLUMN, self.DEC_COLUMN):
                widget = self.table.cellWidget(row, column)
                if widget is not None:
                    widget.setEnabled(not catalog)

    def _run_network(self, operation, succeeded, label: str) -> None:
        if self._thread is not None:
            QMessageBox.information(self, label, "別の処理が実行中です。")
            return
        self.solve_status.setText(f"{label}中...")
        self.solve_button.setEnabled(False)
        self.catalog_search_button.setEnabled(False)
        self.ephemeris_button.setEnabled(False)
        thread = QThread(self)
        worker = _NetworkWorker(operation)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.succeeded.connect(succeeded)
        worker.failed.connect(lambda exc: QMessageBox.critical(self, f"{label}エラー", str(exc)))
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._network_finished)
        self._thread = thread
        self._worker = worker
        thread.start()

    @Slot()
    def _network_finished(self) -> None:
        self._thread = None
        self._worker = None
        self.solve_button.setEnabled(True)
        self._update_mode_widgets()

    def _search_catalog(self) -> None:
        self._ephemeris_ready = False
        query = self.catalog_query.text()
        self._run_network(
            lambda: SmallBodyCatalog().search(query),
            self._catalog_search_succeeded,
            "カタログ検索",
        )

    @Slot(object)
    def _catalog_search_succeeded(self, results: list[CatalogObject]) -> None:
        self._catalog_results = results
        self.catalog_results.clear()
        for result in results:
            kind = "彗星" if result.kind and result.kind.startswith("c") else "小惑星/小天体"
            self.catalog_results.addItem(f"{result.fullname}  [{kind}]", result)
        self.solve_status.setText(f"検索完了: {len(results)}件")
        if not results:
            QMessageBox.information(
                self, "カタログ検索", "該当する小天体が見つかりませんでした。"
            )

    def _corrected_midpoints(self) -> list[datetime]:
        self._apply_time_correction()
        return [
            self._corrected_starts[frame.info.path]
            + timedelta(seconds=float(frame.info.exposure_time or 0.0) / 2.0)
            for frame in self.frames
        ]

    def _calculate_ephemeris(self) -> None:
        target = self.catalog_results.currentData()
        if not isinstance(target, CatalogObject):
            QMessageBox.information(
                self,
                "軌道計算",
                "先にカタログから天体を検索・選択してください。",
            )
            return
        times = self._corrected_midpoints()
        observer = self.observer_code.text().strip() or "500"
        self._run_network(
            lambda: HorizonsEphemeris().positions(target, times, observer),
            self._ephemeris_succeeded,
            "軌道計算",
        )

    @Slot(object)
    def _ephemeris_succeeded(self, positions) -> None:
        for row, position in enumerate(positions):
            ra = self.table.cellWidget(row, self.RA_COLUMN)
            dec = self.table.cellWidget(row, self.DEC_COLUMN)
            checkbox = self.table.cellWidget(row, self.ANCHOR_COLUMN)
            if isinstance(ra, QDoubleSpinBox):
                ra.setValue(position.ra_deg)
            if isinstance(dec, QDoubleSpinBox):
                dec.setValue(position.dec_deg)
            if isinstance(checkbox, QCheckBox):
                checkbox.setChecked(True)
        self._ephemeris_ready = len(positions) == len(self.frames)
        self.solve_status.setText(f"軌道計算完了: {len(positions)}時刻")

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
        reference_path = Path(self.alignment_reference.currentData())
        frame = next((item for item in self.frames if item.info.path == reference_path), None)
        if frame is None:
            QMessageBox.information(self, "Plate Solve", "基準画像を選択してください。")
            return

        row = self.frames.index(frame)
        ra_widget = self.table.cellWidget(row, self.RA_COLUMN)
        dec_widget = self.table.cellWidget(row, self.DEC_COLUMN)
        checkbox = self.table.cellWidget(row, self.ANCHOR_COLUMN)
        use_hint = (
            isinstance(ra_widget, QDoubleSpinBox)
            and isinstance(dec_widget, QDoubleSpinBox)
            and isinstance(checkbox, QCheckBox)
            and checkbox.isChecked()
            and (
                self.mode.currentData() == MovingObjectMode.MANUAL
                or self._ephemeris_ready
            )
        )

        settings = PlateSolveSettings(
            executable=self.executable.text().strip() or "solve-field",
            downsample=self.downsample.value(),
            center_ra_deg=ra_widget.value() if use_hint else None,
            center_dec_deg=dec_widget.value() if use_hint else None,
            search_radius_deg=8.0,
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
        self._apply_time_correction()
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
        if self.mode.currentData() == MovingObjectMode.CATALOG:
            if not isinstance(self.catalog_results.currentData(), CatalogObject):
                QMessageBox.warning(self, "移動天体カタログ", "カタログ天体を選択してください。")
                return
            if len(anchors) != len(self.frames) or not self._ephemeris_ready:
                QMessageBox.warning(
                    self,
                    "軌道計算が必要です",
                    "全画像の座標がありません。「選択天体の軌道位置を計算」を実行してください。",
                )
                return

        self.project.set_reference_image(reference)
        self.project.settings.alignment.reference_mode = ReferenceMode.MANUAL
        moving = self.project.settings.moving_object
        moving.mode = self.mode.currentData()
        moving.anchors = anchors
        moving.reference_frame_path = Path(self.moving_reference.currentData())
        selected = self.catalog_results.currentData()
        moving.catalog_object = selected if isinstance(selected, CatalogObject) else None
        moving.observer_code = self.observer_code.text().strip() or "500"
        apply_corrected_capture_starts(self.frames, self._corrected_starts)
        super().accept()

    def reject(self) -> None:
        if isinstance(self._worker, _PlateSolveWorker):
            self._worker.cancel()
            self.solve_status.setText("キャンセル中...")
            return
        if self._worker is not None:
            QMessageBox.information(self, "処理中", "通信処理の完了を待ってください。")
            return
        super().reject()
