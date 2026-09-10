"""Optional exposure and robust background normalization."""

import numpy as np

from ..core.frame_provider import FrameProvider
from ..io.image_data import AstroImage


def background_level(image: np.ndarray, method: str = "median") -> float:
    data = np.asarray(image, dtype=np.float32)
    if data.ndim == 3:
        data = np.mean(data, axis=-1)
    finite = data[np.isfinite(data)]
    if not finite.size:
        raise ValueError("Cannot estimate background from an invalid image")
    if method == "median":
        return float(np.median(finite))
    if method == "robust":
        median = float(np.median(finite))
        deviation = np.abs(finite - median)
        mad = float(np.median(deviation))
        keep = deviation <= max(1e-8, 3.0 * 1.4826 * mad)
        return float(np.median(finite[keep])) if np.any(keep) else median
    if method.startswith("percentile:"):
        percentile = float(method.partition(":")[2])
        return float(np.percentile(finite, np.clip(percentile, 0, 100)))
    raise ValueError(f"Unknown background normalization method: {method}")


def normalize_image(
    image: np.ndarray,
    *,
    exposure_time: float | None = None,
    target_background: float | None = None,
    background_method: str = "median",
) -> np.ndarray:
    result = np.asarray(image, dtype=np.float32).copy()
    if exposure_time is not None:
        if not np.isfinite(exposure_time) or exposure_time <= 0:
            raise ValueError("Exposure time must be positive")
        result /= exposure_time
    if target_background is not None:
        result += float(target_background) - background_level(result, background_method)
    return result


class NormalizedFrameProvider:
    def __init__(
        self,
        base_provider: FrameProvider,
        *,
        exposure: bool = False,
        background_method: str = "none",
        target_background: float | None = None,
    ):
        self.base_provider = base_provider
        self.exposure = exposure
        self.background_method = background_method
        self.target_background = target_background

    def get_image(self, astro_image: AstroImage) -> np.ndarray:
        exposure = astro_image.info.exposure_time if self.exposure else None
        target = self.target_background if self.background_method != "none" else None
        return normalize_image(
            self.base_provider.get_image(astro_image),
            exposure_time=exposure,
            target_background=target,
            background_method=(
                self.background_method if self.background_method != "none" else "median"
            ),
        )
