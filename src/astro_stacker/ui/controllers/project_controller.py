from pathlib import Path

from PySide6.QtCore import QObject, Signal

from ...project.project import Project


class ProjectController(QObject):
    """
    UIとProjectを仲介する。
    """

    project_changed = Signal()
    category_count_changed = Signal(str, int)

    def __init__(self):
        super().__init__()

        self.project = Project()

    def get_count(self, category: str) -> int:
        return len(getattr(self.project, category))

    def add_file(
        self,
        category: str,
        path: Path,
    ) -> None:
        frames = getattr(self.project, category)

        frames.append(path)

        count = len(frames)

        self.category_count_changed.emit(
            category,
            count,
        )

        self.project_changed.emit()