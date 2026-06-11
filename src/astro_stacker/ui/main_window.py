# main_window.py

from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QSplitter,
)
from PySide6.QtCore import Qt

from .viewer.image_viewer import ImageViewer
from .panels.frame_table import FrameTable
from .panels.info_panel import InfoPanel
from .panels.log_panel import LogPanel


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()

        self.setWindowTitle("Astro Stacker")
        self.resize(1400, 900)

        self._build_ui()

    def _build_ui(self):

        central = QWidget()
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)

        center_splitter = QSplitter(Qt.Orientation.Horizontal)

        self.viewer = ImageViewer()
        self.info_panel = InfoPanel()

        center_splitter.addWidget(self.viewer)
        center_splitter.addWidget(self.info_panel)

        center_splitter.setStretchFactor(0, 1)

        self.frame_table = FrameTable()
        self.log_panel = LogPanel()

        main_splitter = QSplitter(Qt.Orientation.Vertical)

        main_splitter.addWidget(center_splitter)
        main_splitter.addWidget(self.frame_table)
        main_splitter.addWidget(self.log_panel)

        main_splitter.setStretchFactor(0, 1)

        layout.addWidget(main_splitter)