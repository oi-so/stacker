"""Mask transforms that exactly match image alignment geometry."""

from __future__ import annotations

import cv2
import numpy as np

from ..io.image_data import AstroImage, TransformData


def transform_mask(mask: np.ndarray, transform: TransformData | None) -> np.ndarray:
    """Apply an image transform to a boolean mask with nearest-neighbour sampling.

    Interpolated fractional weights would expand/soften a user-approved region,
    so masks deliberately use nearest-neighbour sampling and are boolean on
    return.  Pixels introduced from outside the source frame are invalid.
    """
    source = np.asarray(mask, dtype=np.uint8)
    if source.ndim != 2:
        raise ValueError("Obstacle masks must be two-dimensional")
    if transform is None or transform.matrix is None:
        return source.astype(bool, copy=True)
    matrix = np.asarray(transform.matrix, dtype=np.float64)
    if matrix.shape != (3, 3) or not np.isfinite(matrix).all():
        raise ValueError("Obstacle transform must be a finite 3x3 matrix")
    height, width = source.shape
    if np.allclose(matrix[2], (0.0, 0.0, 1.0)):
        moved = cv2.warpAffine(
            source, matrix[:2], (width, height), flags=cv2.INTER_NEAREST,
            borderMode=cv2.BORDER_CONSTANT, borderValue=0,
        )
    else:
        moved = cv2.warpPerspective(
            source, matrix, (width, height), flags=cv2.INTER_NEAREST,
            borderMode=cv2.BORDER_CONSTANT, borderValue=0,
        )
    return moved.astype(bool)


class TrackedObstacleMaskProvider:
    """Expose a reference obstacle mask as output-grid stack weights.

    This provider is intentionally applied *after* image alignment.  It must
    therefore not be wrapped in ``AlignedMaskProvider`` a second time.
    """

    def __init__(self, reference_mask: np.ndarray):
        self.reference_mask = np.asarray(reference_mask, dtype=bool)

    def get_mask(self, astro_image: AstroImage, shape: tuple[int, int]) -> np.ndarray:
        if self.reference_mask.shape != shape:
            raise ValueError("Tracked obstacle mask shape does not match image shape")
        blocked = transform_mask(self.reference_mask, astro_image.info.transform)
        return (~blocked).astype(np.float32)
