from pathlib import Path

from PySide6.QtCore import QObject, Signal

from ...project.project import Project
from ...io.loader import load_info
from ..constants import FrameType, MASTER_TO_FRAME_TYPE



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
    category_count_changed = Signal(object, int)
    selected_frame_type_changed = Signal(object)
    frames_changed = Signal(list)
    all_frames_changed = Signal(object)

    def __init__(self):
        super().__init__()

        self.project = Project()
        self.selected_frame_type = FrameType.LIGHT


    def _get_frame_list(self, frame_type: FrameType):
        return self.CATEGORY_MAP[frame_type](self.project)

    def get_count(self, frame_type: FrameType) -> int:
        return len(self._get_frame_list(frame_type))

    def add_file(self, frame_type: FrameType, path: Path) -> None:
        if path in self.project.known_paths: return
        image = load_info(path)
        if image.info.master_type in MASTER_TO_FRAME_TYPE:
            frame_type = MASTER_TO_FRAME_TYPE[image.info.master_type]

        self.project.known_paths.add(path)
        frames = self._get_frame_list(frame_type)
        frames.append(image)

        self.category_count_changed.emit(
            frame_type,
            len(frames),
        )

        self.project_changed.emit()
        self.frames_changed.emit(frames)
        self.all_frames_changed.emit(self.frame_map())

    def add_files(self, frame_type: FrameType, paths: list[Path]) -> None:
        for path in paths:
            self.add_file(frame_type, path)
        self.all_frames_changed.emit(self.frame_map())

    
    def set_selected_frames_type(self, frame_type: FrameType) -> None:
        if self.selected_frame_type == frame_type: return

        self.selected_frame_type = frame_type
        self.selected_frame_type_changed.emit(frame_type)
        frames = self.get_frames(frame_type)
        self.frames_changed.emit(frames)


    def get_frames(self, frame_type: FrameType):
        return self._get_frame_list(frame_type)

    def frame_map(self) -> dict[FrameType, list]:
        return {frame_type: self.get_frames(frame_type) for frame_type in FrameType}

    def reset(self) -> None:
        self.project = Project()
        self.project_changed.emit()
        self.all_frames_changed.emit(self.frame_map())
        for frame_type in FrameType:
            self.category_count_changed.emit(frame_type, 0)
    
