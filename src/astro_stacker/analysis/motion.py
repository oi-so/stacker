"""Star/ground relative-motion summary and reversal candidate detection."""

from dataclasses import dataclass
from itertools import pairwise

import numpy as np

from ..io.image_data import AstroImage


@dataclass(frozen=True)
class MotionAnalysis:
    star_motion: bool
    star_pixels_per_frame: float
    star_direction: tuple[float, float]
    ground_pixels_per_frame: float | None
    relative_pixels_per_frame: float | None
    reversal_candidates: tuple[int, ...]
    recommendation: str
    confidence: float


@dataclass(frozen=True)
class GroupSuggestion:
    split_indices: tuple[int, ...]
    groups: tuple[tuple[int, int], ...]
    reason: str
    confidence: float


def _translations(matrices) -> np.ndarray:
    values = []
    for matrix in matrices:
        if matrix is None:
            values.append((np.nan, np.nan))
        else:
            array = np.asarray(matrix, dtype=float)
            values.append((array[0, 2], array[1, 2]))
    return np.asarray(values, dtype=float)


def analyze_motion(
    frames: list[AstroImage],
    ground_matrices: list[np.ndarray | None] | None = None,
    *,
    movement_threshold: float = 0.1,
) -> MotionAnalysis:
    """Analyze per-frame alignment vectors already measured by reusable aligners."""
    if len(frames) < 2:
        raise ValueError("Motion analysis requires at least two frames")
    star_positions = _translations([
        frame.info.transform.matrix if frame.info.transform is not None else None
        for frame in frames
    ])
    star_steps = np.diff(star_positions, axis=0)
    valid_star = np.isfinite(star_steps).all(axis=1)
    if not np.any(valid_star):
        raise ValueError("Motion analysis requires aligned frame transforms")
    star_vector = np.median(star_steps[valid_star], axis=0)
    star_speed = float(np.median(np.linalg.norm(star_steps[valid_star], axis=1)))
    ground_speed = relative_speed = None
    comparison_steps = star_steps
    if ground_matrices is not None:
        if len(ground_matrices) != len(frames):
            raise ValueError("Ground transform count does not match frame count")
        ground_steps = np.diff(_translations(ground_matrices), axis=0)
        valid_ground = np.isfinite(ground_steps).all(axis=1)
        if np.any(valid_ground):
            ground_vector = np.median(ground_steps[valid_ground], axis=0)
            ground_speed = float(np.linalg.norm(ground_vector))
            relative = star_steps - ground_steps
            valid_relative = np.isfinite(relative).all(axis=1)
            if np.any(valid_relative):
                relative_speed = float(np.median(np.linalg.norm(relative[valid_relative], axis=1)))
                comparison_steps = relative
    valid = np.isfinite(comparison_steps).all(axis=1)
    vectors = comparison_steps[valid]
    candidates = []
    valid_indices = np.flatnonzero(valid)
    for index in range(1, len(vectors)):
        before, after = vectors[index - 1], vectors[index]
        if np.linalg.norm(before) > movement_threshold and np.dot(before, after) < 0:
            candidates.append(int(valid_indices[index] + 1))
    completeness = float(valid_star.sum() / len(star_steps))
    if relative_speed is not None and relative_speed > movement_threshold:
        recommendation = "star_alignment"
    elif ground_speed is not None and ground_speed > star_speed:
        recommendation = "ground_alignment"
    elif star_speed > movement_threshold:
        recommendation = "star_alignment"
    else:
        recommendation = "no_alignment"
    return MotionAnalysis(
        star_motion=star_speed > movement_threshold,
        star_pixels_per_frame=star_speed,
        star_direction=(float(star_vector[0]), float(star_vector[1])),
        ground_pixels_per_frame=ground_speed,
        relative_pixels_per_frame=relative_speed,
        reversal_candidates=tuple(candidates),
        recommendation=recommendation,
        confidence=completeness,
    )


def suggest_time_groups(analysis: MotionAnalysis, frame_count: int) -> GroupSuggestion:
    """Convert measured reversal candidates into reviewable frame ranges."""
    splits = tuple(
        sorted({index for index in analysis.reversal_candidates if 0 < index < frame_count})
    )
    boundaries = (0, *splits, frame_count)
    groups = tuple(pairwise(boundaries))
    if splits:
        reason = "星と地上の相対移動方向が反転する候補を検出しました。"
    else:
        reason = "明確な移動方向反転は検出されませんでした。"
    return GroupSuggestion(splits, groups, reason, analysis.confidence)
