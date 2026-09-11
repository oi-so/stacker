"""Data objects for reviewable, frame-scoped obstacle masks."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

import numpy as np


class MaskSource(StrEnum):
    MANUAL = "manual"
    AUTO = "auto"
    TRACKED = "tracked"


@dataclass(frozen=True)
class MaskInterval:
    """Inclusive interval in the project's ordered enabled-Light list."""

    start_frame: int
    end_frame: int

    def contains(self, index: int) -> bool:
        return self.start_frame <= index <= self.end_frame


@dataclass
class ObstacleMask:
    """One obstacle region; ``True`` means exclude it from stack statistics."""

    mask: np.ndarray
    confidence: np.ndarray | None = None
    label: str | None = None
    source: MaskSource = MaskSource.MANUAL
    interval: MaskInterval | None = None
    frame_paths: frozenset[Path] | None = None

    def __post_init__(self) -> None:
        self.mask = np.asarray(self.mask, dtype=bool)
        if self.mask.ndim != 2:
            raise ValueError("Obstacle masks must be two-dimensional")
        if self.confidence is not None:
            self.confidence = np.asarray(self.confidence, dtype=np.float32)
            if self.confidence.shape != self.mask.shape:
                raise ValueError("Obstacle confidence must match mask shape")
            np.clip(self.confidence, 0, 1, out=self.confidence)

    def applies_to(self, frame_index: int, path: Path | None = None) -> bool:
        if self.interval is not None and not self.interval.contains(frame_index):
            return False
        return self.frame_paths is None or (path is not None and path in self.frame_paths)


@dataclass
class ObstacleMaskSet:
    masks: list[ObstacleMask] = field(default_factory=list)

    def combined_mask(
        self, shape: tuple[int, int], *, frame_index: int = 0, path: Path | None = None
    ) -> np.ndarray:
        result = np.zeros(shape, dtype=bool)
        for obstacle in self.masks:
            if not obstacle.applies_to(frame_index, path):
                continue
            if obstacle.mask.shape != shape:
                raise ValueError("Obstacle mask shape does not match image shape")
            result |= obstacle.mask
        return result
