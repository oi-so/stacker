# main_window.py

from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QSplitter,
)
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QFileDialog
from PySide6.QtCore import Qt
from pathlib import Path

from .viewer.image_viewer import ImageViewer
from .panels.frame_table import FrameTable
from .panels.info_panel import InfoPanel
from .panels.log_panel import LogPanel
from .panels.project_tree import ProjectTree
from .controllers.project_controller import ProjectController
from .constants import FrameType


IMAGE_PATH = f"{str(Path.cwd())}/test_images"



class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()

        self.setWindowTitle("Astro Stacker")
        self.resize(1400, 900)

        self._build_ui()


    def _on_add_light_frames(self, frame_type: FrameType):
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            f"Select {frame_type.display_name} Frames",
            "",
            (
                "Images (*.fits *.fit *.fts "
                "*.arw *.cr2 *.cr3 *.nef "
                "*.tif *.tiff)"
            )
        )

        if not paths:
            return

        self.controller.add_files(
            frame_type,
            [Path(p) for p in paths],
        )

    def _create_file_menu(self):
        file_menu = self.menuBar().addMenu("File")

        for frame_type in FrameType:
            action = QAction(f"Add {frame_type.display_name}", self)
            action.triggered.connect(
                lambda checked=False, ft=frame_type: self._on_add_light_frames(ft)
            )
            file_menu.addAction(action)


    def _create_menu(self):
        self._create_file_menu()

    def _build_ui(self):

        central = QWidget()
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)

        center_splitter = QSplitter(
            Qt.Orientation.Horizontal
        )

        self.project_tree = ProjectTree()
        self.viewer = ImageViewer()
        self.info_panel = InfoPanel()
        self.controller = ProjectController()

        self.controller.category_count_changed.connect(self.project_tree.set_count)

        center_splitter.addWidget(self.project_tree)
        center_splitter.addWidget(self.viewer)
        center_splitter.addWidget(self.info_panel)

        center_splitter.setStretchFactor(1, 1)

        self.frame_table = FrameTable()
        self.log_panel = LogPanel()

        main_splitter = QSplitter(Qt.Orientation.Vertical)

        main_splitter.addWidget(center_splitter)
        main_splitter.addWidget(self.frame_table)
        main_splitter.addWidget(self.log_panel)

        main_splitter.setStretchFactor(0, 1)

        layout.addWidget(main_splitter)

        self._create_menu()

