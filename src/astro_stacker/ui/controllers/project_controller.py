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
        self.add_files(frame_type, [path])

    def add_files(self, frame_type: FrameType, paths: list[Path]) -> None:
        # Reading metadata is independent. Update Qt models once per batch,
        # keeping every model mutation and signal on the caller's GUI thread.
        from concurrent.futures import ThreadPoolExecutor

        paths = list(dict.fromkeys(Path(path).resolve() for path in paths))
        paths = [path for path in paths if path not in self.project.known_paths]
        if not paths:
            return
        changed = set()
        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                for image in executor.map(load_info, paths):
                    category = MASTER_TO_FRAME_TYPE.get(image.info.master_type, frame_type)
                    self.project.known_paths.add(image.info.path)
                    self._get_frame_list(category).append(image)
                    if category != FrameType.LIGHT:
                        setattr(self.project.settings.calibration, "use_" + category.value, True)
                    changed.add(category)
        finally:
            # Also refresh successfully loaded frames if a later file fails.
            for category in changed:
                self.category_count_changed.emit(category, self.get_count(category))
            if changed:
                from ...io.history import adopt_alignment_history
                adopt_alignment_history(self.project)
                self.project_changed.emit()
                self.frames_changed.emit(self.get_frames(self.selected_frame_type))
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
    

    def remove_frames(self, frame_type: FrameType, images) -> None:
        frames = self._get_frame_list(
            frame_type
        )

        changed = False

        for image in images:
            try:
                frames.remove(image)
                self.project.known_paths.discard(
                    image.info.path
                )
                changed = True
            except ValueError:
                pass

        if not changed:
            return

        self.category_count_changed.emit(
            frame_type,
            len(frames),
        )

        self.project_changed.emit()

        self.frames_changed.emit(
            frames
        )

        self.all_frames_changed.emit(
            self.frame_map()
        )
