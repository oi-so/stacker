"""Nightscape material generation and star-protected final compositing."""

import cv2
import numpy as np


def _material_array(image: np.ndarray) -> np.ndarray:
    data = np.asarray(image, dtype=np.float32)
    if data.ndim == 3 and data.shape[-1] == 1:
        return data[..., 0]
    return data


def light_pollution_frame(
    image: np.ndarray,
    star_mask: np.ndarray | None = None,
    *,
    blur_scale: float = 32.0,
) -> np.ndarray:
    data = _material_array(image)
    source = data.copy()
    if star_mask is not None:
        mask = (np.asarray(star_mask, dtype=np.float32) > 0.05).astype(np.uint8) * 255
        if mask.shape != data.shape[:2]:
            raise ValueError("Star mask shape does not match image")
        if data.ndim == 3:
            channels = [cv2.inpaint(data[..., c], mask, 3, cv2.INPAINT_TELEA) for c in range(data.shape[-1])]
            source = np.stack(channels, axis=-1)
        else:
            source = cv2.inpaint(data, mask, 3, cv2.INPAINT_TELEA)
    return cv2.GaussianBlur(source, (0, 0), max(0.1, float(blur_scale)))


def composite_nightscape(
    sky: np.ndarray,
    ground: np.ndarray,
    sky_weight: np.ndarray,
    *,
    star_mask: np.ndarray | None = None,
    pollution_frame: np.ndarray | None = None,
    background_strength: float = 0.0,
) -> tuple[np.ndarray, np.ndarray]:
    sky_data = _material_array(sky)
    ground_data = _material_array(ground)
    if sky_data.shape != ground_data.shape:
        raise ValueError("Sky and ground material must have the same shape")
    weight = np.clip(np.asarray(sky_weight, dtype=np.float32), 0, 1)
    if weight.shape != sky_data.shape[:2]:
        raise ValueError("Ground mask shape does not match materials")
    if star_mask is not None:
        stars = np.clip(np.asarray(star_mask, dtype=np.float32), 0, 1)
        if stars.shape != weight.shape:
            raise ValueError("Star mask shape does not match materials")
        # Preserve complete stars that intersect a feathered horizon.
        weight = np.maximum(weight, stars * (weight > 0).astype(np.float32))
    blend_sky = sky_data
    if pollution_frame is not None and background_strength:
        pollution = _material_array(pollution_frame)
        if pollution.shape != sky_data.shape:
            raise ValueError("Light-pollution frame shape does not match materials")
        blend_sky = sky_data + pollution * float(background_strength) * (1.0 - weight[..., None] if sky_data.ndim == 3 else 1.0 - weight)
    channel_weight = weight[..., None] if sky_data.ndim == 3 else weight
    result = blend_sky * channel_weight + ground_data * (1.0 - channel_weight)
    return result.astype(np.float32), weight
