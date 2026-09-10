"""Exposure grouping and linear radiance HDR merge."""

from dataclasses import dataclass

import cv2
import numpy as np

from ..io.image_data import AstroImage


@dataclass(frozen=True)
class ExposureGroup:
    exposure_time: float
    iso: int | None
    f_number: float | None
    frames: tuple[AstroImage, ...]


def group_by_exposure(frames: list[AstroImage], tolerance: float = 0.01) -> list[ExposureGroup]:
    """Group by exposure/ISO/aperture with relative exposure tolerance."""
    groups: list[list[AstroImage]] = []
    tolerance = max(0.0, float(tolerance))
    for frame in frames:
        exposure = frame.info.exposure_time
        if exposure is None or not np.isfinite(exposure) or exposure <= 0:
            raise ValueError(f"Missing exposure time: {frame.info.path}")
        match = None
        for group in groups:
            leader = group[0]
            base = leader.info.exposure_time or 0.0
            same_exposure = abs(exposure - base) <= tolerance * max(exposure, base)
            if (
                same_exposure
                and frame.info.iso == leader.info.iso
                and frame.info.f_number == leader.info.f_number
            ):
                match = group
                break
        (match if match is not None else groups.append([]) or groups[-1]).append(frame)
    result = [
        ExposureGroup(
            exposure_time=float(group[0].info.exposure_time),
            iso=group[0].info.iso,
            f_number=group[0].info.f_number,
            frames=tuple(group),
        )
        for group in groups
    ]
    return sorted(result, key=lambda group: group.exposure_time)


def group_manually(
    frames: list[AstroImage], assignments: dict[str, str]
) -> list[ExposureGroup]:
    """Group frames by user labels while retaining exposure metadata for merge."""
    grouped: dict[str, list[AstroImage]] = {}
    for frame in frames:
        key = assignments.get(str(frame.info.path))
        if key is None or not str(key).strip():
            raise ValueError(f"Manual HDR group is missing for {frame.info.path}")
        grouped.setdefault(str(key).strip(), []).append(frame)
    result = []
    for members in grouped.values():
        exposures = [frame.info.exposure_time for frame in members]
        if any(value is None or value <= 0 for value in exposures):
            raise ValueError("Manual HDR groups still require positive exposure metadata")
        exposure = float(np.median(np.asarray(exposures, dtype=float)))
        result.append(
            ExposureGroup(exposure, members[0].info.iso, members[0].info.f_number, tuple(members))
        )
    return sorted(result, key=lambda group: group.exposure_time)


def _levels(images: list[np.ndarray], black_level, white_level) -> tuple[float, float]:
    finite = np.concatenate([
        np.asarray(image, dtype=np.float32)[np.isfinite(image)][:: max(1, image.size // 100_000)]
        for image in images
    ])
    if not finite.size:
        raise ValueError("HDR inputs contain no finite pixels")
    black = float(np.percentile(finite, 0.1)) if black_level is None else float(black_level)
    white = float(np.percentile(finite, 99.9)) if white_level is None else float(white_level)
    if not np.isfinite(black) or not np.isfinite(white) or white <= black:
        raise ValueError("HDR white level must be greater than black level")
    return black, white


def merge_hdr(
    images: list[np.ndarray],
    exposure_times: list[float],
    *,
    masks: list[np.ndarray] | None = None,
    black_level: float | None = None,
    white_level: float | None = None,
    is_cancelled=None,
) -> tuple[np.ndarray, np.ndarray]:
    """Merge aligned linear exposure stacks into radiance and validity mask."""
    if not images or len(images) != len(exposure_times):
        raise ValueError("HDR requires one positive exposure time per image")
    shape = np.asarray(images[0]).shape
    if any(np.asarray(image).shape != shape for image in images):
        raise ValueError("All HDR inputs must have the same shape")
    if masks is not None and len(masks) != len(images):
        raise ValueError("HDR mask count does not match image count")
    black, white = _levels(images, black_level, white_level)
    numerator = np.zeros(shape, dtype=np.float64)
    weight_sum = np.zeros(shape[:2], dtype=np.float64)
    for index, (image, exposure) in enumerate(zip(images, exposure_times, strict=True)):
        if is_cancelled and is_cancelled():
            raise InterruptedError("HDR merge cancelled")
        if not np.isfinite(exposure) or exposure <= 0:
            raise ValueError("HDR exposure times must be positive")
        data = np.asarray(image, dtype=np.float32)
        level = np.clip((data - black) / (white - black), 0.0, 1.0)
        # Smooth triangular response: dark and saturated samples approach zero.
        weight = np.sin(np.pi * level) ** 2
        if data.ndim == 3:
            weight2d = np.min(weight, axis=-1)
        else:
            weight2d = weight
        weight2d *= np.isfinite(data).all(axis=-1) if data.ndim == 3 else np.isfinite(data)
        if masks is not None:
            mask = np.asarray(masks[index], dtype=np.float32)
            if mask.shape != shape[:2]:
                raise ValueError("HDR mask shape does not match image")
            weight2d *= np.clip(mask, 0.0, 1.0)
        broadcast = weight2d[..., None] if data.ndim == 3 else weight2d
        radiance = np.nan_to_num(data / exposure, nan=0.0, posinf=0.0, neginf=0.0)
        numerator += radiance * broadcast
        weight_sum += weight2d
    denominator = weight_sum[..., None] if numerator.ndim == 3 else weight_sum
    hdr = np.zeros(shape, dtype=np.float32)
    np.divide(numerator, denominator, out=hdr, where=denominator > 0)
    return hdr, (weight_sum > 0).astype(np.float32)


def tone_map(
    image: np.ndarray,
    method: str = "global",
    strength: float = 1.0,
    *,
    local_scale: float = 32.0,
    detail_strength: float = 1.0,
) -> np.ndarray:
    """Tone-map linear HDR data while preserving RGB chromaticity."""
    data = np.clip(np.asarray(image, dtype=np.float32), 0.0, None)
    luminance = np.mean(data, axis=-1) if data.ndim == 3 else data
    finite = luminance[np.isfinite(luminance)]
    if not finite.size:
        return np.zeros_like(data)
    scale = max(float(np.percentile(finite, 99)), 1e-8)
    normalized = luminance / scale
    if method == "global":
        mapped_luminance = normalized / (
            1.0 + max(1e-6, strength) * normalized
        )
    elif method == "log":
        mapped_luminance = np.log1p(max(1e-6, strength) * normalized) / np.log1p(
            max(1e-6, strength)
        )
    elif method == "local":
        log_luminance = np.log1p(normalized)
        base = cv2.GaussianBlur(
            log_luminance,
            (0, 0),
            max(0.5, float(local_scale)),
            borderType=cv2.BORDER_REFLECT,
        )
        detail = log_luminance - base
        dynamic_range = float(np.percentile(base, 99.5) - np.percentile(base, 0.5))
        compressed = base / max(1.0, dynamic_range * max(0.1, float(strength)))
        mapped_luminance = np.expm1(
            compressed + detail * max(0.0, float(detail_strength))
        )
        mapped_values = mapped_luminance[np.isfinite(mapped_luminance)]
        if mapped_values.size:
            mapped_luminance /= float(np.percentile(mapped_values, 99.5)) + 1e-8
    else:
        raise ValueError(f"Unknown tone mapping method: {method}")
    if data.ndim == 3:
        ratio = mapped_luminance / np.maximum(normalized, 1e-8)
        mapped = data / scale * ratio[..., None]
    else:
        mapped = mapped_luminance
    return np.clip(mapped, 0.0, 1.0).astype(np.float32)
