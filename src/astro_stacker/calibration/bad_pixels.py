"""Hot/cold pixel and abnormal-column detection with CFA-safe correction."""

import numpy as np
from scipy.ndimage import median_filter

from ..core.frame_provider import FrameProvider
from ..io.image_data import AstroImage, CFAType


def detect_bad_pixels(
    dark_or_bias: np.ndarray,
    *,
    hot_sigma: float = 8.0,
    cold_sigma: float = 8.0,
    detect_columns: bool = True,
) -> np.ndarray:
    data = np.asarray(dark_or_bias, dtype=np.float32)
    if data.ndim == 3 and data.shape[-1] == 1:
        data = data[..., 0]
    if data.ndim != 2:
        raise ValueError("Bad pixel detection expects a mono/Bayer master frame")
    local = median_filter(data, size=5, mode="reflect")
    residual = data - local
    median = float(np.nanmedian(residual))
    mad = float(np.nanmedian(np.abs(residual - median)))
    noise = max(1e-8, 1.4826 * mad)
    bad = (residual > hot_sigma * noise) | (residual < -cold_sigma * noise)
    if detect_columns:
        column_level = np.nanmedian(residual, axis=0)
        column_mad = float(np.nanmedian(np.abs(column_level - np.nanmedian(column_level))))
        column_noise = max(1e-8, 1.4826 * column_mad)
        abnormal = np.abs(column_level - np.nanmedian(column_level)) > hot_sigma * column_noise
        bad[:, abnormal] = True
    return bad.astype(np.float32)


def correct_bad_pixels(
    image: np.ndarray,
    bad_pixel_map: np.ndarray,
    *,
    cfa_type: CFAType = CFAType.NONE,
    method: str = "median",
) -> np.ndarray:
    data = np.asarray(image, dtype=np.float32)
    squeeze = data.ndim == 3 and data.shape[-1] == 1
    work = data[..., 0] if squeeze else data
    bad = np.asarray(bad_pixel_map) > 0
    if bad.shape != work.shape[:2]:
        raise ValueError("Bad pixel map shape does not match image")
    if method not in {"median", "bilinear"}:
        raise ValueError(f"Unknown bad-pixel interpolation: {method}")
    result = work.copy()
    stride = 2 if cfa_type != CFAType.NONE else 1
    radius = 2 * stride
    for y, x in np.argwhere(bad):
        y0, y1 = max(0, y - radius), min(work.shape[0], y + radius + 1)
        x0, x1 = max(0, x - radius), min(work.shape[1], x + radius + 1)
        yy, xx = np.mgrid[y0:y1, x0:x1]
        same_cfa = ((yy - y) % stride == 0) & ((xx - x) % stride == 0)
        usable = same_cfa & ~bad[y0:y1, x0:x1]
        values = work[y0:y1, x0:x1][usable]
        if values.size:
            if method == "median":
                result[y, x] = np.median(values, axis=0)
            else:
                distances = np.hypot(yy[usable] - y, xx[usable] - x)
                weights = 1.0 / np.maximum(distances, 1e-6)
                result[y, x] = np.average(values, axis=0, weights=weights)
    return result[..., np.newaxis] if squeeze else result


class BadPixelCorrectedFrameProvider:
    """Lazy correction wrapper; the original frame array is never modified."""

    def __init__(self, base_provider: FrameProvider, bad_pixel_map: np.ndarray, method="median"):
        self.base_provider = base_provider
        self.bad_pixel_map = np.asarray(bad_pixel_map, dtype=np.float32)
        self.method = method

    def get_image(self, astro_image: AstroImage) -> np.ndarray:
        return correct_bad_pixels(
            self.base_provider.get_image(astro_image),
            self.bad_pixel_map,
            cfa_type=astro_image.info.cfa_type,
            method=self.method,
        )
