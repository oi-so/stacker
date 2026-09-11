"""Reusable non-overlapping and sliding frame windows."""

from dataclasses import dataclass

from ..io.image_data import AstroImage


@dataclass(frozen=True)
class FrameWindow:
    index: int
    start: int
    stop: int
    frames: tuple[AstroImage, ...]


def make_windows(
    frames: list[AstroImage], window_size: int, step: int | None = None, include_partial: bool = True
) -> list[FrameWindow]:
    if window_size < 1:
        raise ValueError("window_size must be at least 1")
    step = window_size if step is None else step
    if step < 1:
        raise ValueError("step must be at least 1")
    result = []
    for start in range(0, len(frames), step):
        chunk = frames[start : start + window_size]
        if len(chunk) < window_size and not include_partial:
            break
        if not chunk:
            break
        result.append(FrameWindow(len(result) + 1, start, start + len(chunk), tuple(chunk)))
    return result
