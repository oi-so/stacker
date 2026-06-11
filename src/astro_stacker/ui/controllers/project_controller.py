from pathlib import Path

from PySide6.QtCore import QObject, Signal

from ...project.project import Project
from ...io.loader import load_info
from ..constants import FrameType



class ProjectController(QObject):
    """
    UIとProjectを仲介する。
    """

    CATEGORY_MAP = {
        FrameType.LIGHT: lambda p: p.light_frames,
        FrameType.DARK: lambda p: p.calibration_frames.darks,
        FrameType.FLAT: lambda p: p.calibration_frames.flats,
        FrameType.FLAT_DARK: lambda p: p.calibration_frames.flat_darks,
        FrameType.BIAS: lambda p: p.calibration_frames.biases,
    }

    project_changed = Signal()
    category_count_changed = Signal(str, int)

    def __init__(self):
        super().__init__()

        self.project = Project()

    def _get_frame_list(self, frame_type: FrameType):
        return self.CATEGORY_MAP[frame_type](self.project)

    def get_count(self, frame_type: FrameType) -> int:
        return len(self._get_frame_list(frame_type))

    def add_file(self, frame_type: FrameType, path: Path) -> None:
        image = load_info(path)
        if path in self.project.known_paths: return

        self.project.known_paths.add(path)
        frames = self._get_frame_list(frame_type)
        frames.append(image)

        self.category_count_changed.emit(
            frame_type,
            len(frames),
        )

        self.project_changed.emit()

    def add_files(self, frame_type: FrameType, paths: list[Path]):
        for path in paths:
            self.add_file(frame_type, path)