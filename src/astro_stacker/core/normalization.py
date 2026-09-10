"""Linear exposure and robust background normalization."""

import numpy as np


def estimate_background(image: np.ndarray, method: str = "median") -> float:
    values = np.asarray(image, dtype=np.float32)
    values = values[np.isfinite(values)]
    if not values.size:
        return 0.0
    if method == "median":
        return float(np.median(values))
    if method == "percentile":
        return float(np.percentile(values, 25))
    if method == "robust":
        low, high = np.percentile(values, (10, 70))
        clipped = values[(values >= low) & (values <= high)]
        return float(np.median(clipped)) if clipped.size else float(np.median(values))
    if method == "none":
        return 0.0
    raise ValueError(f"Unknown background method: {method}")


def normalize_image(
    image: np.ndarray,
    *,
    exposure_time: float | None = None,
    normalize_exposure: bool = False,
    background_method: str = "none",
    target_background: float = 0.0,
) -> np.ndarray:
    result = np.asarray(image, dtype=np.float32).copy()
    if normalize_exposure:
        if exposure_time is None or not np.isfinite(exposure_time) or exposure_time <= 0:
            raise ValueError("A positive exposure time is required for exposure normalization")
        result /= exposure_time
    if background_method != "none":
        result += target_background - estimate_background(result, background_method)
    return result
