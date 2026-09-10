from __future__ import annotations

from pathlib import Path

LAST_DIRECTORY_KEY = "dialogs/last_directory"


def last_dialog_directory(settings, fallback: Path | str | None = None) -> Path:
    """Return the most recently selected, still-existing dialog directory."""
    saved = settings.value(LAST_DIRECTORY_KEY, "", str)
    if saved:
        directory = Path(saved).expanduser()
        if directory.is_dir():
            return directory

    candidate = Path(fallback or Path.cwd()).expanduser()
    if candidate.is_file() or not candidate.is_dir() and candidate.parent.is_dir():
        candidate = candidate.parent
    return candidate if candidate.is_dir() else Path.cwd()


def remember_dialog_path(settings, path: Path | str, *, directory: bool = False) -> None:
    """Remember the containing directory of a selected file or directory."""
    selected = Path(path).expanduser()
    selected_directory = selected if directory else selected.parent
    settings.setValue(LAST_DIRECTORY_KEY, str(selected_directory))
