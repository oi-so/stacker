from PySide6.QtWidgets import QTableWidget, QTableWidgetItem
from ..constants import FrameType
from ...io.image_data import AstroImage


class FrameTable(QTableWidget):

    def __init__(self):
        super().__init__()

    def show_frames(
        self,
        frames: list[AstroImage],
    ) -> None:

        self.setRowCount(len(frames))

        for row, image in enumerate(frames):

            self.setItem(
                row,
                0,
                QTableWidgetItem(
                    image.info.path.name
                )
            )