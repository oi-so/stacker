"""Deterministic quality weighting and non-destructive frame selection."""

import math
from pathlib import Path

import numpy as np

from ..io.image_data import AstroImage
from ..project.settings import FrameSelectionMode, FrameSelectionSettings


def frame_quality_weight(frame: AstroImage) -> float:
    """Map available quality metrics to [0, 1]; missing metrics are neutral."""
    score = frame.info.score_data
    terms: list[float] = []
    if score.fwhm is not None and score.fwhm > 0:
        terms.append(1.0 / score.fwhm)
    if score.star_count is not None:
        terms.append(math.log1p(max(0, score.star_count)))
    if score.ellipticity is not None:
        terms.append(max(0.0, 1.0 - score.ellipticity))
    if score.background_noise is not None and score.background_noise >= 0:
        terms.append(1.0 / (score.background_noise + 1e-6))
    if score.cloud_score is not None:
        terms.append(max(0.0, 1.0 - score.cloud_score))
    rms = frame.info.alignment_data.rms_error
    if rms is not None and rms >= 0:
        terms.append(1.0 / (1.0 + rms))
    if score.score is not None and np.isfinite(score.score):
        terms.append(max(0.0, score.score))
    if not terms:
        return 1.0
    # Geometric mean prevents one metric's units dominating by summation.
    return float(math.exp(sum(math.log(max(1e-6, value)) for value in terms) / len(terms)))


def quality_weights(
    frames: list[AstroImage], user_weights: dict[Path, float] | None = None
) -> dict[Path, float]:
    raw = np.asarray([frame_quality_weight(frame) for frame in frames], dtype=np.float64)
    finite = raw[np.isfinite(raw) & (raw > 0)]
    scale = float(np.percentile(finite, 90)) if finite.size else 1.0
    result = {}
    for frame, value in zip(frames, raw, strict=True):
        weight = float(np.clip(value / max(scale, 1e-12), 0.0, 1.0))
        if user_weights and frame.info.path in user_weights:
            weight *= float(np.clip(user_weights[frame.info.path], 0.0, 1.0))
        result[frame.info.path] = weight
    return result


def select_frames(
    frames: list[AstroImage], settings: FrameSelectionSettings
) -> tuple[list[AstroImage], dict[Path, str]]:
    """Return a selection and reasons without changing ``frame.info.enabled``."""
    candidates = [frame for frame in frames if frame.info.enabled]
    if settings.mode in {FrameSelectionMode.ALL, FrameSelectionMode.MANUAL}:
        return candidates, {}
    weighted = quality_weights(candidates)
    ordered = sorted(candidates, key=lambda frame: weighted[frame.info.path], reverse=True)
    if settings.mode == FrameSelectionMode.TOP_PERCENT:
        keep = max(1, math.ceil(len(ordered) * np.clip(settings.value, 0, 100) / 100))
        selected = ordered[:keep]
    elif settings.mode == FrameSelectionMode.TOP_COUNT:
        selected = ordered[: max(0, int(settings.value))]
    elif settings.mode == FrameSelectionMode.SCORE_THRESHOLD:
        selected = [frame for frame in ordered if weighted[frame.info.path] >= settings.value]
    else:
        selected = ordered
    selected_paths = {frame.info.path for frame in selected}
    reasons = {
        frame.info.path: f"quality weight {weighted[frame.info.path]:.3f} did not meet selection"
        for frame in candidates if frame.info.path not in selected_paths
    }
    return selected, reasons
