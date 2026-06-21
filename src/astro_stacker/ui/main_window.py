from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QObject, QSettings, QThread, Qt, Signal, Slot
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QFileDialog,
    QMainWindow,
    QProgressBar,
    QSplitter,
    QToolBar,
    QWidget,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QTabWidget,
    QHBoxLayout,
)

from ..core.provider import ImageManagerProvider
from ..io.image_manager import ImageManager
from ..io.saver import save_image
from ..pipeline.alignment_pipeline import AlignmentPipeline
from ..pipeline.processing_pipeline import ProcessingPipeline
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
from .viewer.image_viewer import ImageViewer
from ..core.debayer import debayer

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
            self.failed.emit(exc)
        finally:
            self.finished.emit()

    def cancel(self):
        self.cancel_requested = True



class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings("AstroStacker", "AstroStacker")
        self.manager = ImageManager(max_loaded_image_count=10)
        self.controller = ProjectController()
        self._thread: QThread | None = None
        self._worker: PipelineWorker | None = None
        self._aligned = False
        self._stacked = False

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
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress_label = QLabel("準備完了")
        self.cancel_button = QPushButton("キャンセル")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(lambda: self._worker.cancel())

        progress_layout = QHBoxLayout()
        progress_layout.addWidget(self.progress_label)
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
        self.platesolve_action = QAction("🔭\nPlate Solve\n(将来実装)", self)
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
        self.stack_action.triggered.connect(self._run_stacking)
        self.save_action.triggered.connect(self._save_result)
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

    def _create_menu(self):
        file_menu = self.menuBar().addMenu("ファイル")
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

    def _connect_signals(self):
        self.controller.category_count_changed.connect(self.project_tree.set_count)
        self.controller.all_frames_changed.connect(lambda _: self._refresh_tables())
        self.project_tree.frame_type_selected.connect(lambda ft: self.frame_table.tabs.setCurrentIndex(list(FrameType).index(ft)))
        self.frame_table.files_dropped.connect(self.controller.add_files)
        self.frame_table.frame_selected.connect(self._preview_frame)
        self.frame_table.enabled_changed.connect(lambda *_: self._update_actions())
        self.frame_table.removed.connect(self.controller.remove_frames)
        self.frame_table.selection_cleared.connect(self.viewer.set_image(None))

        def on_reference_changed(image):
            self.project_tree.update_reference_image_display(image)
            self._refresh_tables()

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
        if image is None:
            self.viewer.set_image(None)
            return

        try:
            nd_img = self.manager.get_image(image)
            nd_img = (
                nd_img[0::2, 0::2]
                + nd_img[0::2, 1::2]
                + nd_img[1::2, 0::2]
                + nd_img[1::2, 1::2]
            ) / 4
            nd_img = debayer(nd_img, image.info.cfa_type)
            self.viewer.set_image(nd_img)
        except Exception as exc:
            ErrorDialog.show_exception(self, "画像表示エラー", exc)

    def _run_alignment(self):
        if AlignmentSettingsDialog(self.controller.project, self).exec() != AlignmentSettingsDialog.DialogCode.Accepted:
            return

        def work(progress, is_cancelled):
            provider = ImageManagerProvider(self.manager)
            AlignmentPipeline(provider).run(self.controller.project, self.controller.project.settings.alignment, progress=progress, is_cancelled=is_cancelled)

        self._run_worker(work, on_success=self._alignment_finished)

    def _run_stacking(self):
        if StackingSettingsDialog(self.controller.project, self).exec() != StackingSettingsDialog.DialogCode.Accepted:
            return

        def work(progress, is_cancelled):
            ProcessingPipeline(self.manager).run(self.controller.project, progress=progress, is_cancelled=is_cancelled)

        self._run_worker(work, on_success=self._stacking_finished)


    def _run_worker(self, func, on_success):
        self.progress.setRange(0, 0)
        self.progress_label.setText("処理中...")
        self.cancel_button.setEnabled(True)

        self._set_busy(True)
        thread = QThread(self)
        worker = PipelineWorker(func)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        # worker.failed.connect(lambda exc: ErrorDialog.show_exception(self, "処理エラー", exc))
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.progress.connect(self._update_progress)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda: self._worker_done(on_success))
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
        on_success()
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
            save_image(result, path, **kwargs)
            logger.info("保存しました: %s", path)
        except Exception as exc:
            ErrorDialog.show_exception(self, "保存エラー", exc)

    def _reset_project(self):
        self.controller.reset()

        def on_reference_changed(image):
            self.project_tree.update_reference_image_display(image)
            self._refresh_tables()

        self.controller.project.on_reference_image_changed = on_reference_changed
        on_reference_changed(None)

        self.manager.unload_all()
        self.viewer.set_image(None)
        self._aligned = False
        self._stacked = False
        self._update_actions()

    def _set_busy(self, busy: bool):
        for action in (self.add_action, self.align_action, self.stack_action, self.save_action, self.reset_action):
            action.setEnabled(not busy)
        self.frame_table.setEnabled(not busy)
        self.project_tree.setEnabled(not busy)
        self.bottom_tabs.setEnabled(not busy)

    def _update_actions(self):
        has_lights = bool(self.controller.project.light_frames)
        self.align_action.setEnabled(has_lights)
        self.stack_action.setEnabled(has_lights)
        self.save_action.setEnabled(self.controller.project.result.stacked_image is not None)
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
