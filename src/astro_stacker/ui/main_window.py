from __future__ import annotations

import logging
from datetime import datetime
from dataclasses import asdict
from pathlib import Path

from PySide6.QtCore import QObject, QSettings, Qt, QThread, Signal, Slot
from PySide6.QtGui import QAction, QTransform
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QInputDialog,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from ..alignment.transform import ImageTransformer
from ..core.provider import ImageManagerProvider, PreviewProvider, PreviewSettings
from ..io.image_manager import ImageManager
from ..io.saver import save_image
from ..moving_object.marker import moving_object_preview_pixel
from ..pipeline.alignment_pipeline import AlignmentPipeline
from ..pipeline.processing_pipeline import ProcessingPipeline
from ..platesolve import AstrometryNetSolver, PlateSolveSettings
from .constants import FrameType
from .controllers.project_controller import ProjectController
from .dialogs import (
    AlignmentSettingsDialog,
    ErrorDialog,
    SaveDialog,
    StackingSettingsDialog,
    show_language_restart,
)
from .panels.frame_table import FrameTable
from .panels.info_panel import InfoPanel
from .panels.log_panel import LogPanel, QtLogHandler
from .panels.project_tree import ProjectTree
from .viewer.image_viewer import ImageViewer, StarDisplayMode

logger = logging.getLogger(__name__)


class PipelineWorker(QObject):
    finished = Signal()
    failed = Signal(object)

    progress = Signal(str, int, int, str)

    def __init__(self, func):
        super().__init__()
        self.func = func
        self.cancel_requested = False

    @Slot()
    def run(self):
        try:
            self.func(
                self.progress.emit,
                lambda: self.cancel_requested
            )
        except Exception as exc:
            logger.exception("Pipeline failed")
            self.failed.emit(exc)
        finally:
            self.finished.emit()

    def cancel(self):
        self.cancel_requested = True



class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._dirty = False
        self._restoring = False
        self._busy = False
        self._showing_result = False
        self.settings = QSettings("AstroStacker", "AstroStacker")
        self.manager = ImageManager(max_loaded_image_count=10)
        self.controller = ProjectController()
        self._thread: QThread | None = None
        self._worker: PipelineWorker | None = None
        self._aligned = False
        self._stacked = False
        self._selected_frame = None
        self.preview_provider = PreviewProvider(self.manager, ImageTransformer())
        self.preview_settings = PreviewSettings()

        self.setWindowTitle("Astro Stacker")
        self.resize(1400, 900)
        self._build_ui()
        self._restore_window()
        self._install_logging()


    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        self.project_tree = ProjectTree()
        self.viewer = ImageViewer()
        self.info_panel = InfoPanel()
        self.frame_table = FrameTable()
        self.log_panel = LogPanel()

        self.bottom_tabs = QTabWidget()
        self.bottom_tabs.addTab(self.frame_table, "フレーム一覧")
        self.bottom_tabs.addTab(self.log_panel, "ログ")
        self.log_panel.append_log(logging.INFO, "Started Astro Stacker!!")
        self.log_panel.append_log(logging.INFO, f"Started at: {datetime.now().strftime('%Y/%m/%d %H:%M:%S')}")

        center_splitter = QSplitter(Qt.Orientation.Horizontal)
        center_splitter.addWidget(self.project_tree)
        center_splitter.addWidget(self.viewer)
        center_splitter.addWidget(self.info_panel)
        center_splitter.setStretchFactor(1, 1)

        main_splitter = QSplitter(Qt.Orientation.Vertical)
        main_splitter.addWidget(center_splitter)
        main_splitter.addWidget(self.bottom_tabs)
        main_splitter.setStretchFactor(0, 1)

        self.progress = QProgressBar()
        self.progress.setMinimumHeight(20)
        self.progress.setTextVisible(True)
        self.progress.setStyleSheet("""
            QProgressBar {
                border: 1px solid palette(mid);
                border-radius: 4px;
                text-align: center;
            }

            QProgressBar::chunk {
                background-color: #3B82F6;
                border-radius: 3px;
            }
        """)
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress_label = QLabel("準備完了")
        self.cancel_button = QPushButton("キャンセル")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self._cancel_worker)

        progress_layout = QHBoxLayout()
        progress_layout.addWidget(self.progress_label)
        progress_layout.addStretch()
        self.progress.setFixedWidth(250)
        progress_layout.addWidget(self.progress, 1)
        progress_layout.addWidget(self.cancel_button)

        layout.addWidget(main_splitter)
        layout.addLayout(progress_layout)

        self._create_toolbar()
        self._create_menu()
        self._connect_signals()
        self._refresh_tables()
        self._update_actions()

    def _create_toolbar(self):
        toolbar = QToolBar("Main")
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.addToolBar(toolbar)

        self.zoom_out_button = QPushButton("－")
        self.zoom_label = QLabel("100%")
        self.zoom_in_button = QPushButton("＋")
        self.zoom_100_button = QPushButton("100%")
        self.zoom_fit_button = QPushButton("Fit")

        self.add_action = QAction("📂\nフレーム追加", self)
        self.align_action = QAction("▶\n位置合わせ", self)
        self.stack_action = QAction("⚙\nスタック", self)
        self.save_action = QAction("💾\n保存", self)
        self.platesolve_action = QAction("🔭\nPlate Solve", self)
        self.reset_action = QAction("❌\nリセット", self)
        self.platesolve_action.setEnabled(False)

        for action in (
            self.add_action,
            self.align_action,
            self.stack_action,
            self.save_action,
            self.platesolve_action,
            self.reset_action,
        ):
            toolbar.addAction(action)

        self.add_action.triggered.connect(
            lambda: self._on_add_frames(self.frame_table.current_frame_type())
        )
        self.align_action.triggered.connect(self._run_alignment)
        self.stack_action.triggered.connect(self._on_stack)
        self.save_action.triggered.connect(self._save_result)
        self.platesolve_action.triggered.connect(self._run_plate_solve)
        self.reset_action.triggered.connect(self._reset_project)


        toolbar.addWidget(self.zoom_out_button)
        toolbar.addWidget(self.zoom_label)
        toolbar.addWidget(self.zoom_in_button)
        toolbar.addWidget(self.zoom_100_button)
        toolbar.addWidget(self.zoom_fit_button)

        self.zoom_out_button.clicked.connect(
            lambda: self.viewer.set_zoom(
                self.viewer.zoom_percent() / 1.25
            )
        )

        self.zoom_in_button.clicked.connect(
            lambda: self.viewer.set_zoom(
                self.viewer.zoom_percent() * 1.25
            )
        )

        self.zoom_100_button.clicked.connect(
            lambda: self.viewer.set_zoom(100)
        )

        self.zoom_fit_button.clicked.connect(
            self.viewer.fit_image
        )
        self.viewer.zoom_changed.connect(
            lambda z:
                self.zoom_label.setText(f"{z:.0f}%")
        )

        toolbar.addSeparator()
        self.show_stars_checkbox = QCheckBox("星")
        self.star_mode_combo = QComboBox()
        self.star_mode_combo.addItems(["全星", "位置合わせ星"])
        self.star_mode_combo.setEnabled(False)
        toolbar.addWidget(self.show_stars_checkbox)
        toolbar.addWidget(self.star_mode_combo)

        self.show_stars_checkbox.toggled.connect(
            self._on_show_stars_changed
        )

        self.star_mode_combo.currentIndexChanged.connect(
            self._on_star_mode_changed
        )


    def _create_menu(self):
        file_menu = self.menuBar().addMenu("ファイル")
        self.project_open_action = QAction("プロジェクトを開く...", self)
        self.project_open_action.setShortcut("Ctrl+O")
        self.project_open_action.triggered.connect(self._open_project)
        self.project_save_action = QAction("プロジェクトを保存", self)
        self.project_save_action.setShortcut("Ctrl+S")
        self.project_save_action.triggered.connect(lambda: self._save_project())
        self.project_save_as_action = QAction("プロジェクトを名前を付けて保存...", self)
        self.project_save_as_action.setShortcut("Ctrl+Shift+S")
        self.project_save_as_action.triggered.connect(lambda: self._save_project(save_as=True))
        self.project_notes_action = QAction("プロジェクトのメモ...", self)
        self.project_notes_action.triggered.connect(self._edit_project_notes)
        self.project_history_action = QAction("位置合わせ履歴...", self)
        self.project_history_action.triggered.connect(self._show_project_history)
        for action in self._project_actions():
            file_menu.addAction(action)
        file_menu.addSeparator()
        for frame_type in FrameType:
            action = QAction(f"{frame_type.ja_name}を追加", self)
            action.triggered.connect(lambda checked=False, ft=frame_type: self._on_add_frames(ft))
            file_menu.addAction(action)

        settings_menu = self.menuBar().addMenu("設定")
        language_menu = settings_menu.addMenu("言語 / Language")
        japanese = QAction("日本語", self)
        english = QAction("English", self)
        japanese.triggered.connect(lambda: self._set_language("ja"))
        english.triggered.connect(lambda: self._set_language("en"))
        language_menu.addAction(japanese)
        language_menu.addAction(english)

    def _project_actions(self):
        return (self.project_open_action, self.project_save_action, self.project_save_as_action,
                self.project_notes_action, self.project_history_action)

    def _mark_dirty(self, *_):
        if self._restoring:
            return
        if not self.controller.project.known_paths and not self.controller.project.notes and not self.controller.project.project_path:
            return
        self._dirty = True
        self.setWindowTitle(f"Astro Stacker — {self.controller.project.project_name} *")

    def _capture_view(self):
        transform = self.viewer.transform()
        self.controller.project.view_state = {
            "selected": self._selected_frame.info.path if self._selected_frame else None,
            "category": self.frame_table.current_frame_type().value,
            "preview": asdict(self.preview_settings), "result": self._showing_result,
            "show_stars": self.show_stars_checkbox.isChecked(),
            "star_mode": self.star_mode_combo.currentIndex(),
            "zoom": [transform.m11(), transform.m12(), transform.m21(), transform.m22(),
                     transform.dx(), transform.dy()],
            "scroll": [self.viewer.horizontalScrollBar().value(), self.viewer.verticalScrollBar().value()],
            "plate_settings": {key: self.settings.value("platesolve/" + key, default, kind)
                for key, default, kind in [("executable", "solve-field", str), ("downsample", 2, int),
                    ("auto_downsample", True, bool), ("timeout", 180, int)]},
        }

    def _save_project(self, save_as=False):
        from ..project.storage import save_project
        path = self.controller.project.project_path
        if save_as or path is None:
            name, _ = QFileDialog.getSaveFileName(self, "プロジェクトを保存",
                str(path or Path.cwd() / "Untitled.astrostacker"), "Astro Stacker (*.astrostacker)")
            if not name:
                return False
            path = Path(name)
            if path.suffix.lower() != ".astrostacker":
                path = path.with_name(path.name + ".astrostacker")
        try:
            self._capture_view()
            save_project(self.controller.project, path)
            self._dirty = False
            self.setWindowTitle(f"Astro Stacker — {path.stem}")
            return True
        except Exception as exc:
            ErrorDialog.show_exception(self, "プロジェクト保存エラー", exc)
            return False

    def _confirm_discard(self):
        if not self._dirty:
            return True
        choice = QMessageBox.question(self, "未保存のプロジェクト",
            "プロジェクトの変更を保存しますか？",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel)
        if choice == QMessageBox.StandardButton.Save:
            return self._save_project()
        return choice == QMessageBox.StandardButton.Discard

    def _open_project(self):
        from ..project.storage import load_project
        name, _ = QFileDialog.getOpenFileName(self, "プロジェクトを開く", "", "Astro Stacker (*.astrostacker)")
        if not name or not self._confirm_discard():
            return
        try:
            project, warnings = load_project(Path(name))
        except Exception as exc:
            ErrorDialog.show_exception(self, "プロジェクト読み込みエラー", exc)
            return
        self._install_project(project)
        if warnings:
            QMessageBox.warning(self, "プロジェクトの復元", "\n".join(warnings))

    def _install_project(self, project):
        self._restoring = True
        try:
            self.manager.unload_all()
            self.controller.project = project
            self._selected_frame = None
            def reference_changed(image):
                self.project_tree.update_reference_image_display(image)
                self._refresh_tables()
                self._mark_dirty()
            project.on_reference_image_changed = reference_changed
            # Resolve the project at signal time rather than retaining an old bound method.
            self._refresh_tables()
            self.project_tree.update_reference_image_display(project.reference_image)
            for category in FrameType:
                self.project_tree.set_count(category, self.controller.get_count(category))
            view = project.view_state
            self.preview_settings = PreviewSettings(**view.get("preview", {}))
            self.frame_table.tabs.setCurrentIndex(list(FrameType).index(FrameType(view.get("category", "lights"))))
            self.show_stars_checkbox.setChecked(view.get("show_stars", False))
            self.star_mode_combo.setCurrentIndex(view.get("star_mode", 0))
            for key, value in view.get("plate_settings", {}).items():
                self.settings.setValue("platesolve/" + key, value)
            from ..project.storage import frame_groups
            selected = next((f for frames in frame_groups(project).values() for f in frames
                             if view.get("selected") is not None and f.info.path.resolve() == Path(view["selected"]).resolve() and f.info.path.exists()), None)
            self._preview_frame(selected)
            if selected is not None:
                self.frame_table.select_frame(selected)
            self._showing_result = bool(view.get("result") and project.result.stacked_image is not None)
            if self._showing_result:
                self.viewer.set_image(project.result.stacked_image)
            if "zoom" in view:
                self.viewer.setTransform(QTransform(*view["zoom"]))
                self.viewer._fit_mode = False
            if "scroll" in view:
                self.viewer.horizontalScrollBar().setValue(view["scroll"][0])
                self.viewer.verticalScrollBar().setValue(view["scroll"][1])
            self._aligned = project.is_alignment_valid()
            self._stacked = project.result.stacked_image is not None
            self._update_actions()
        finally:
            self._restoring = False
        self._dirty = False
        self.setWindowTitle(f"Astro Stacker — {project.project_name}")

    def _edit_project_notes(self):
        text, accepted = QInputDialog.getMultiLineText(self, "プロジェクトのメモ", "撮影・処理メモ", self.controller.project.notes)
        if accepted:
            self.controller.project.notes = text
            self._mark_dirty()

    def _show_project_history(self):
        sessions = self.controller.project.alignment_sessions.values()
        text = "\n".join(f"{s.created_at.isoformat()}  基準: {s.reference_name}  [{s.session_id}]" for s in sessions)
        QMessageBox.information(self, "位置合わせ履歴", text or "保存された履歴はありません。")

    def _connect_signals(self):
        self.controller.project_changed.connect(self._mark_dirty)
        self.frame_table.enabled_changed.connect(self._mark_dirty)
        self.viewer.zoom_changed.connect(self._mark_dirty)
        self.frame_table.tabs.currentChanged.connect(self._mark_dirty)
        self.show_stars_checkbox.toggled.connect(self._mark_dirty)
        self.star_mode_combo.currentIndexChanged.connect(self._mark_dirty)
        self.controller.category_count_changed.connect(self.project_tree.set_count)
        self.controller.all_frames_changed.connect(lambda _: self._refresh_tables())
        self.project_tree.frame_type_selected.connect(lambda ft: self.frame_table.tabs.setCurrentIndex(list(FrameType).index(ft)))
        self.frame_table.files_dropped.connect(self.controller.add_files)
        self.frame_table.frame_selected.connect(self._preview_frame)
        self.frame_table.enabled_changed.connect(lambda *_: self._update_actions())
        self.frame_table.removed.connect(self.controller.remove_frames)
        self.frame_table.selection_cleared.connect(lambda *_: self._preview_frame(None))
        self.frame_table.reference_image_requested.connect(lambda image: self.controller.project.set_reference_image(image))

        def on_reference_changed(image):
            self.project_tree.update_reference_image_display(image)
            self._refresh_tables()
            self._mark_dirty()

        self.controller.project.on_reference_image_changed = on_reference_changed
        on_reference_changed(self.controller.project.reference_image)

    def _install_logging(self):
        handler = QtLogHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
        handler.emitter.message.connect(self.log_panel.append_log)
        root = logging.getLogger()
        root.setLevel(logging.INFO)
        root.addHandler(handler)
        self._qt_log_handler = handler

    
    def _on_show_stars_changed(self, checked: bool):
        self.star_mode_combo.setEnabled(checked)

        if not checked:
            self.viewer.set_star_display_mode(StarDisplayMode.NONE)
            return

        self._on_star_mode_changed(self.star_mode_combo.currentIndex())

    def _on_star_mode_changed(self, index: int):
        if not self.show_stars_checkbox.isChecked():
            return

        mode = (
            StarDisplayMode.ALL if index == 0 else StarDisplayMode.ALIGNMENT
        )
        self.viewer.set_star_display_mode(mode)

    def _cancel_worker(self):
        if self._worker:
            self._worker.cancel()


    def _on_add_frames(self, frame_type: FrameType):
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            f"{frame_type.ja_name}を追加",
            "",
            "Images (*.fits *.fit *.fts *.arw *.cr2 *.cr3 *.nef *.raf *.png *.jpg *.jpeg *.tif *.tiff)",
        )
        if paths:
            self.controller.add_files(frame_type, [Path(path) for path in paths])
            self._update_actions()

    def _refresh_tables(self):
        self.frame_table.set_frames(self.controller.frame_map(), self.controller.project.reference_image)

    def _preview_frame(self, image):
        self._showing_result = False
        if image is not self._selected_frame:
            self._mark_dirty()
        self._selected_frame = image
        self._update_actions()
        if image is None:
            self.viewer.set_image(None)
            return

        try:
            preview = self.preview_provider.get_image(image, self.preview_settings)
            marker = moving_object_preview_pixel(
                self.controller.project,
                image,
                aligned=self.preview_settings.aligned and image.info.is_aligned,
                scale_x=preview.scale_x,
                scale_y=preview.scale_y,
            )
            self.viewer.set_image(
                preview.image,
                preview.all_stars,
                preview.alignment_stars,
                preview.scale_x,
                preview.scale_y,
                marker,
                )
        except Exception as exc:
            ErrorDialog.show_exception(self, "画像表示エラー", exc)


    def _show_stack_dialog(self, use_aligned_image: bool | None = None) -> bool:
        dialog = StackingSettingsDialog(
            self.controller.project,
            self.manager,
            self,
            use_aligned_image=use_aligned_image,
        )
        accepted = dialog.exec() == StackingSettingsDialog.DialogCode.Accepted
        if accepted:
            self._mark_dirty()
        if self._selected_frame is not None:
            self._preview_frame(self._selected_frame)
        return accepted
    
    def _show_alignment_dialog(self) -> bool:
        accepted = AlignmentSettingsDialog(self.controller.project, self).exec() == AlignmentSettingsDialog.DialogCode.Accepted
        if accepted:
            self._mark_dirty()
        return accepted

    def _run_alignment(self):
        if not self._show_alignment_dialog():
            return

        def work(progress, is_cancelled):
            provider = ImageManagerProvider(self.manager)
            AlignmentPipeline(provider).run(self.controller.project, self.controller.project.settings.alignment, progress=progress, is_cancelled=is_cancelled)

        self._run_worker(work, on_success=self._alignment_finished)
        self.viewer.viewport().update()

    def _run_plate_solve(self):
        frame = self._selected_frame
        if frame is None:
            QMessageBox.information(self, "Plate Solve", "フレーム一覧から画像を選択してください。")
            return

        settings = PlateSolveSettings(
            executable=self.settings.value("platesolve/executable", "solve-field", str),
            downsample=self.settings.value("platesolve/downsample", 2, int),
            timeout_seconds=self.settings.value("platesolve/timeout", 180, int),
            auto_downsample=self.settings.value("platesolve/auto_downsample", True, bool),
        )
        result_holder = {}

        def work(progress, is_cancelled):
            progress("Plate Solve", 0, 1, frame.info.path.name)
            result_holder["result"] = AstrometryNetSolver().solve(
                frame,
                ImageManagerProvider(self.manager),
                settings,
                is_cancelled=is_cancelled,
            )
            progress("Plate Solve", 1, 1, frame.info.path.name)

        def succeeded():
            result = result_holder["result"]
            frame.info.wcs = result.wcs
            logger.info(
                "Plate Solve完了: %s / RA %.6f°, Dec %.6f°, %.3f arcsec/pix",
                frame.info.path.name,
                result.center_ra_deg,
                result.center_dec_deg,
                result.pixel_scale_arcsec,
            )
            if self._selected_frame is frame:
                self._preview_frame(frame)

        self._run_worker(work, on_success=succeeded)

    def _run_stacking(self):
        if not self._show_stack_dialog():
            return

        def work(progress, is_cancelled):
            ProcessingPipeline(self.manager).run(self.controller.project, progress=progress, is_cancelled=is_cancelled)

        self._run_worker(work, on_success=self._stacking_finished)

    @Slot(object)
    def _on_worker_failed_trigger(self, exc):
        """メインスレッド側で安全にエラーダイアログを表示するためのスロット"""
        ErrorDialog.show_exception(self, "処理エラー", exc)

    def _run_worker(self, func, on_success):
        self.progress.setRange(0, 0)
        self.progress_label.setText("処理中...")
        self.cancel_button.setEnabled(True)

        self._set_busy(True)
        thread = QThread(self)
        worker = PipelineWorker(func)
        worker.moveToThread(thread)

        is_success = True
        def handle_failed(exc):
            nonlocal is_success
            is_success = False

        thread.started.connect(worker.run)
        worker.failed.connect(handle_failed)
        worker.failed.connect(self._on_worker_failed_trigger)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.progress.connect(self._update_progress)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda: self._worker_done(on_success if is_success else None))

        worker.finished.connect(
            lambda: logger.info("worker.finished")
        )

        thread.finished.connect(
            lambda: logger.info("thread.finished")
        )

        self._thread = thread
        self._worker = worker
        thread.start()

    def _worker_done(self, on_success):
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress_label.setText("準備完了")
        self.cancel_button.setEnabled(False)
        self._set_busy(False)
        self._refresh_tables()

        if on_success:
            on_success()
        self._mark_dirty()
        
        self._update_actions()
        self._thread = None
        self._worker = None

    def _alignment_finished(self):
        self._aligned = True
        logger.info("位置合わせが完了しました")

    def _stacking_finished(self):
        self._aligned = True
        self._stacked = self.controller.project.result.stacked_image is not None
        if self._stacked:
            self._showing_result = True
            self.viewer.set_image(self.controller.project.result.stacked_image)
        logger.info("スタックが完了しました")

    def _save_result(self):
        result = self.controller.project.result.stacked_image
        if result is None:
            return
        folder = self.controller.project.output_path.parent if self.controller.project.output_path else Path.cwd()
        dialog = SaveDialog(folder, self)
        if dialog.exec() != SaveDialog.DialogCode.Accepted:
            return
        path, kwargs = dialog.selected()
        try:
            metadata = dict(self.controller.project.result.metadata)
            comment = kwargs.pop("comment", "")
            if comment:
                metadata["COMMENT"] = metadata.get("COMMENT", "") + "\n" + comment
            save_image(result, path, metadata=metadata, **kwargs)
            logger.info("保存しました: %s", path)
        except Exception as exc:
            ErrorDialog.show_exception(self, "保存エラー", exc)

    def _reset_project(self):
        if self._confirm_discard():
            from ..project.project import Project
            self._install_project(Project())

    def _set_busy(self, busy: bool):
        self._busy = busy
        for action in self._project_actions():
            action.setEnabled(not busy)
        for action in (
            self.add_action,
            self.align_action,
            self.stack_action,
            self.save_action,
            self.platesolve_action,
            self.reset_action,
        ):
            action.setEnabled(not busy)
        self.frame_table.setEnabled(not busy)
        self.project_tree.setEnabled(not busy)

    def _update_actions(self):
        if self._busy:
            return
        has_lights = bool(self.controller.project.light_frames)
        self.align_action.setEnabled(has_lights)
        self.stack_action.setEnabled(has_lights)
        self.save_action.setEnabled(self.controller.project.result.stacked_image is not None)
        self.platesolve_action.setEnabled(self._selected_frame is not None)
        self.add_action.setEnabled(True)
        self.reset_action.setEnabled(True)

    def _set_language(self, language: str):
        self.settings.setValue("ui/language", language)
        show_language_restart(self)

    def _restore_window(self):
        geometry = self.settings.value("window/geometry")
        state = self.settings.value("window/state")
        if geometry:
            self.restoreGeometry(geometry)
        if state:
            self.restoreState(state)

    def closeEvent(self, event):
        if self._busy:
            QMessageBox.information(self, "処理中", "処理をキャンセルし、終了を待ってから閉じてください。")
            event.ignore()
            return
        if not self._confirm_discard():
            event.ignore()
            return
        self.settings.setValue("window/geometry", self.saveGeometry())
        self.settings.setValue("window/state", self.saveState())
        super().closeEvent(event)

    @Slot(str, int, int, str)
    def _update_progress(self, phase: str, current: int, total: int, message: str):
        self.progress.setRange(0, total)
        self.progress.setValue(current)

        self.progress_label.setText(
            f"{phase} ({current}/{total}) : {message}"
        )

    def _show_unaligned_warning(self):
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("未位置合わせ")
        box.setText(
            "現在のライトフレームは位置合わせされていません。\n\n"
            "比較明合成や固定撮影の星景写真では、そのままスタックできます。"
        )

        stack_btn = box.addButton(
            "そのままスタック",
            QMessageBox.ButtonRole.AcceptRole
        )
        align_btn = box.addButton(
            "位置合わせしてスタック",
            QMessageBox.ButtonRole.ActionRole
        )
        cancel_btn = box.addButton(
            QMessageBox.StandardButton.Cancel
        )

        box.exec()

        clicked = box.clickedButton()

        if clicked is cancel_btn:
            return

        if clicked is stack_btn:
            if not self._show_stack_dialog(use_aligned_image=False):
                return

            def work(progress, is_cancelled):
                ProcessingPipeline(self.manager).run(
                    self.controller.project,
                    progress=progress,
                    is_cancelled=is_cancelled,
                    skip_alignment=True,
                )

            self._run_worker(
                work,
                on_success=self._stacking_finished,
            )
            return

        if clicked is align_btn:
            if not self._show_alignment_dialog(): return
            if not self._show_stack_dialog(use_aligned_image=True): return

            def work(progress, is_cancelled):
                ProcessingPipeline(self.manager).run(
                    self.controller.project,
                    progress=progress,
                    is_cancelled=is_cancelled,
                )

            self._run_worker(
                work,
                on_success=self._stacking_finished,
            )


    def _on_stack(self):
        if self.controller.project.is_alignment_valid():
            self._run_stacking()
        else:
            self._show_unaligned_warning()
