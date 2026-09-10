"""Hot/cold pixel and abnormal-column detection with CFA-safe correction."""

import numpy as np
from scipy.ndimage import label, median_filter

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
    if data.size == 0 or min(data.shape) < 3:
        raise ValueError("Bad pixel detection requires a non-empty 2D frame")
    if not np.isfinite(data).all():
        raise ValueError("Bad pixel detection input contains NaN or infinite values")
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


def detect_bad_pixels_from_lights(
    provider: FrameProvider,
    frames: list[AstroImage],
    *,
    sigma: float = 10.0,
    persistence: float = 0.7,
    progress=None,
    is_cancelled=None,
) -> np.ndarray | None:
    """Detect persistent isolated sensor defects without dark/bias frames.

    This deliberately accepts only mono/Bayer data. Requiring persistence over
    multiple frames and rejecting connected structures reduces the risk of
    treating stars or scene detail as sensor defects.
    """
    enabled = [frame for frame in frames if frame.info.enabled]
    if len(enabled) < 3:
        raise ValueError("LightsからのBad Pixel検出には3枚以上必要です。")
    if not np.isfinite(sigma) or sigma < 3:
        raise ValueError("Bad Pixel検出sigmaは3以上にしてください。")
    if not np.isfinite(persistence) or not 0.3 <= persistence <= 1:
        raise ValueError("Bad Pixel継続率は0.3〜1.0で指定してください。")

    counts = None
    shape = None
    is_bayer = None
    for index, frame in enumerate(enabled, 1):
        if is_cancelled and is_cancelled():
            return None
        data = np.asarray(provider.get_image(frame), dtype=np.float32)
        if data.ndim == 3 and data.shape[-1] == 1:
            data = data[..., 0]
        if data.ndim != 2 or not np.isfinite(data).all():
            raise ValueError("Lights自動検出は有限値のMono/RAW Bayer画像だけに対応します。")
        if shape is None:
            shape = data.shape
            counts = np.zeros(shape, dtype=np.uint16)
            is_bayer = frame.info.cfa_type != CFAType.NONE
        if data.shape != shape:
            raise ValueError("Lightsの画像サイズが一致していません。")
        if (frame.info.cfa_type != CFAType.NONE) != is_bayer:
            raise ValueError("Mono画像とBayer画像を混在させてBad Pixel検出できません。")

        local = np.empty_like(data)
        stride = 2 if is_bayer else 1
        for y in range(stride):
            for x in range(stride):
                plane = data[y::stride, x::stride]
                local[y::stride, x::stride] = median_filter(plane, size=5, mode="reflect")
        residual = data - local
        center = float(np.median(residual))
        noise = max(1e-8, 1.4826 * float(np.median(np.abs(residual - center))))
        counts += (np.abs(residual - center) > sigma * noise).astype(np.uint16)
        if progress:
            progress(
                "LightsからBad Pixel検出中",
                index,
                len(enabled),
                frame.info.path.name,
            )

    required = max(2, int(np.ceil(len(enabled) * persistence)))
    persistent = counts >= required
    isolated = np.zeros(shape, dtype=bool)
    stride = 2 if is_bayer else 1
    for y in range(stride):
        for x in range(stride):
            plane = persistent[y::stride, x::stride]
            components, count = label(plane, structure=np.ones((3, 3), dtype=np.uint8))
            if count:
                sizes = np.bincount(components.ravel())
                keep = (sizes >= 1) & (sizes <= 2)
                keep[0] = False
                isolated[y::stride, x::stride] = keep[components]
    return isolated.astype(np.float32)


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
    mask = np.asarray(bad_pixel_map)
    if mask.ndim == 3 and mask.shape[-1] == 1:
        mask = mask[..., 0]
    if mask.ndim != 2 or not np.isfinite(mask).all():
        raise ValueError("Bad pixel map must be a finite 2D mono image")
    bad = mask > 0
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
