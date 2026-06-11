from pathlib import Path

from PySide6.QtCore import QObject, Signal

from ...project.project import Project
from ...io.loader import load_info



class ProjectController(QObject):
    """
    UIとProjectを仲介する。
    """

    CATEGORY_MAP = {
        "lights": lambda p: p.light_frames,
        "darks": lambda p: p.calibration_frames.darks,
        "flats": lambda p: p.calibration_frames.flats,
        "flat_darks": lambda p: p.calibration_frames.flat_darks,
        "biases": lambda p: p.calibration_frames.biases,
    }

    project_changed = Signal()
    category_count_changed = Signal(str, int)

    def __init__(self):
        super().__init__()

        self.project = Project()

    def _get_frame_list(self, category: str):
        return self.CATEGORY_MAP[category](self.project)

    def get_count(self, category: str) -> int:
        return len(self._get_frame_list(category))

    def add_file(self, category: str, path: Path) -> None:
        image = load_info(path)
        frames = self._get_frame_list(category)
        frames.append(image)

        self.category_count_changed.emit(
            category,
            len(frames),
        )

        self.project_changed.emit()

    def add_files(self, category: str, paths: list[Path]):
        for path in paths:
            self.add_file(category, path)