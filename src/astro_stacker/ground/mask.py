"""Editable horizon-mask primitives and conservative automatic estimation."""

from dataclasses import dataclass

import cv2
import numpy as np
from scipy.ndimage import gaussian_filter1d


@dataclass(frozen=True)
class GroundMaskEstimate:
    sky_weight: np.ndarray
    horizon_y: np.ndarray
    confidence: float
    warning: str | None = None


def estimate_ground_mask(image: np.ndarray, feather: float = 4.0) -> GroundMaskEstimate:
    data = np.asarray(image, dtype=np.float32)
    gray = np.mean(data, axis=-1) if data.ndim == 3 else data
    valid = gray[np.isfinite(gray)]
    if not valid.size:
        raise ValueError("Ground estimation requires finite image pixels")
    finite = np.nan_to_num(
        gray,
        nan=float(np.median(valid)),
        posinf=float(valid.max()),
        neginf=float(valid.min()),
    )
    scaled = cv2.normalize(finite, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    edges = cv2.Canny(scaled, 40, 120).astype(np.float32)
    h, w = gray.shape
    # Ignore image margins; choose the strongest lower-half structural edge per column.
    score = cv2.GaussianBlur(edges, (0, 0), sigmaX=5, sigmaY=2)
    start = max(1, int(h * 0.2))
    horizon = np.argmax(score[start:], axis=0).astype(np.float32) + start
    horizon = gaussian_filter1d(horizon, max(1.0, w / 100.0), mode="nearest")
    strength = score[np.clip(horizon.astype(int), 0, h - 1), np.arange(w)]
    confidence = float(np.clip(np.median(strength) / 64.0, 0.0, 1.0))
    yy = np.arange(h, dtype=np.float32)[:, None]
    width = max(0.25, float(feather))
    sky = np.clip((horizon[None, :] - yy) / width + 0.5, 0.0, 1.0).astype(np.float32)
    warning = None if confidence >= 0.25 else "地上領域の推定信頼度が低いため手動確認が必要です。"
    return GroundMaskEstimate(sky, horizon, confidence, warning)


def polygon_sky_mask(shape: tuple[int, int], ground_polygon, feather: float = 0.0) -> np.ndarray:
    ground = np.zeros(shape, dtype=np.uint8)
    polygon = np.asarray(ground_polygon, dtype=np.int32)
    if polygon.ndim != 2 or polygon.shape[1] != 2 or len(polygon) < 3:
        raise ValueError("Ground polygon requires at least three (x, y) points")
    cv2.fillPoly(ground, [polygon], 255)
    weight = 1.0 - ground.astype(np.float32) / 255.0
    if feather > 0:
        weight = cv2.GaussianBlur(weight, (0, 0), float(feather))
    return np.clip(weight, 0.0, 1.0)
