"""Masks for wires and other narrow, frame-local obstructions."""

from __future__ import annotations

from collections.abc import Iterable

import cv2
import numpy as np

Point = tuple[float, float]
Polyline = list[Point]


def inpaint_masked_pixels(image: np.ndarray, missing: np.ndarray, *, radius: float = 3.0) -> np.ndarray:
    """Fill pixels for which every input frame was deliberately masked.

    A weight mask normally lets the stack use another frame at an obstruction.
    When an obstruction overlaps in every aligned frame, however, the weighted
    stack has no sample at all and used to leave a black stripe.  Inpaint only
    those no-sample pixels; all measured stack pixels are retained unchanged.
    """
    data = np.asarray(image, dtype=np.float32)
    holes = np.asarray(missing, dtype=bool)
    if data.ndim not in (2, 3) or holes.shape != data.shape[:2]:
        raise ValueError("Inpainting mask shape must match the image grid")
    if not np.any(holes):
        return data

    mask = holes.astype(np.uint8) * 255
    result = data.copy()
    if data.ndim == 2:
        return cv2.inpaint(result, mask, radius, cv2.INPAINT_TELEA)
    for channel in range(data.shape[-1]):
        # OpenCV accepts float32 inpainting for one channel at a time.
        result[..., channel] = cv2.inpaint(
            result[..., channel], mask, radius, cv2.INPAINT_TELEA
        )
    return result


def _blocked_to_weight(blocked: np.ndarray, feather: float) -> np.ndarray:
    if not np.any(blocked):
        return np.ones(blocked.shape, dtype=np.float32)
    if feather == 0:
        return (blocked == 0).astype(np.float32)
    distance = cv2.distanceTransform((blocked == 0).astype(np.uint8), cv2.DIST_L2, 5)
    return np.clip(distance / float(feather), 0.0, 1.0).astype(np.float32)


def polyline_weight_mask(
    shape: tuple[int, int],
    polylines: Iterable[Polyline],
    *,
    line_width: float = 8.0,
    feather: float = 3.0,
) -> np.ndarray:
    """Return 0 on marked obstructions and 1 in usable image regions."""
    if len(shape) != 2 or min(shape) <= 0:
        raise ValueError("Mask shape must contain positive height and width")
    if not np.isfinite(line_width) or line_width <= 0:
        raise ValueError("Line width must be positive")
    if not np.isfinite(feather) or feather < 0:
        raise ValueError("Feather must be non-negative")

    blocked = np.zeros(shape, dtype=np.uint8)
    thickness = max(1, round(line_width))
    for polyline in polylines:
        points = np.asarray(list(polyline), dtype=np.float64)
        if len(points) < 2:
            continue
        if points.ndim != 2 or points.shape[1] != 2 or not np.isfinite(points).all():
            raise ValueError("Polyline points must be finite x/y pairs")
        integer_points = np.rint(points).astype(np.int32).reshape((-1, 1, 2))
        cv2.polylines(blocked, [integer_points], False, 1, thickness, cv2.LINE_AA)

    return _blocked_to_weight(blocked, feather)


def polygon_weight_mask(
    shape: tuple[int, int],
    polygons: Iterable[Polyline],
    *,
    feather: float = 3.0,
) -> np.ndarray:
    """Return a weight mask with arbitrary polygonal obstructions removed."""
    if len(shape) != 2 or min(shape) <= 0:
        raise ValueError("Mask shape must contain positive height and width")
    if not np.isfinite(feather) or feather < 0:
        raise ValueError("Feather must be non-negative")
    blocked = np.zeros(shape, dtype=np.uint8)
    for polygon in polygons:
        points = np.asarray(list(polygon), dtype=np.float64)
        if len(points) < 3:
            continue
        if points.ndim != 2 or points.shape[1] != 2 or not np.isfinite(points).all():
            raise ValueError("Polygon points must be finite x/y pairs")
        integer_points = np.rint(points).astype(np.int32).reshape((-1, 1, 2))
        cv2.fillPoly(blocked, [integer_points], 1, cv2.LINE_AA)
    return _blocked_to_weight(blocked, feather)


def detect_line_candidates(
    image: np.ndarray,
    *,
    minimum_length_fraction: float = 0.15,
    maximum_candidates: int = 40,
) -> list[Polyline]:
    """Suggest long dark line segments; the user must review the result."""
    data = np.asarray(image, dtype=np.float32)
    if data.ndim == 3:
        data = np.mean(data, axis=-1)
    if data.ndim != 2 or min(data.shape) < 8:
        raise ValueError("Wire detection expects a 2D image")
    finite = data[np.isfinite(data)]
    if finite.size == 0:
        raise ValueError("Image contains no finite pixels")
    low, high = np.percentile(finite, (1, 99))
    scaled = np.clip((np.nan_to_num(data, nan=low) - low) / max(high - low, 1e-8), 0, 1)
    gray = np.rint(scaled * 255).astype(np.uint8)
    # Black-hat emphasizes thin dark structures without assuming orientation.
    kernel_size = max(9, (min(data.shape) // 80) | 1)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
    enhanced = cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT, kernel)
    edges = cv2.Canny(enhanced, 20, 80)
    minimum_length = max(12, int(min(data.shape) * minimum_length_fraction))
    lines = cv2.HoughLinesP(
        edges,
        1,
        np.pi / 180,
        threshold=max(12, minimum_length // 4),
        minLineLength=minimum_length,
        maxLineGap=max(5, minimum_length // 8),
    )
    if lines is None:
        return []
    candidates = []
    # OpenCV builds return either (N, 1, 4) or (N, 4).
    for x1, y1, x2, y2 in np.asarray(lines).reshape(-1, 4):
        candidates.append([(float(x1), float(y1)), (float(x2), float(y2))])
        if len(candidates) >= maximum_candidates:
            break
    return candidates
