"""Lazy, composable per-pixel weights.

Masks are deliberately providers instead of arrays owned by a project.  This
keeps a many-frame project bounded by the image/cache policy rather than by
``frame_count * image_size`` resident mask memory.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Protocol, runtime_checkable

import numpy as np

from ..alignment.transform import ImageTransformer
from ..io.image_data import AstroImage, TransformData


def _as_mask(mask: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    result = np.asarray(mask, dtype=np.float32)
    if result.ndim == 3 and result.shape[-1] == 1:
        result = result[..., 0]
    if result.shape != shape:
        raise ValueError(f"Mask shape {result.shape} does not match image shape {shape}")
    if not np.isfinite(result).all():
        result = np.nan_to_num(result, nan=0.0, posinf=1.0, neginf=0.0)
    return np.clip(result, 0.0, 1.0)


def compose_masks(masks: Iterable[np.ndarray], shape: tuple[int, int] | None = None) -> np.ndarray:
    """Multiply masks without mutating caller-owned arrays."""
    iterator = iter(masks)
    try:
        first = np.asarray(next(iterator), dtype=np.float32)
    except StopIteration:
        if shape is None:
            raise ValueError("shape is required when composing no masks")
        return np.ones(shape, dtype=np.float32)
    target_shape = shape or first.shape[:2]
    result = _as_mask(first, target_shape).copy()
    for mask in iterator:
        result *= _as_mask(mask, target_shape)
    return np.clip(result, 0.0, 1.0, out=result)


def validity_mask(image: np.ndarray) -> np.ndarray:
    """Return 1 where all channels are finite, otherwise 0."""
    finite = np.isfinite(image)
    if finite.ndim == 3:
        finite = np.all(finite, axis=-1)
    return finite.astype(np.float32)


@runtime_checkable
class WeightMaskProvider(Protocol):
    def get_mask(self, astro_image: AstroImage, shape: tuple[int, int]) -> np.ndarray: ...


class ConstantMaskProvider:
    def __init__(self, value: float = 1.0):
        self.value = float(np.clip(value, 0.0, 1.0))

    def get_mask(self, astro_image: AstroImage, shape: tuple[int, int]) -> np.ndarray:
        return np.full(shape, self.value, dtype=np.float32)


class ArrayMaskProvider:
    """Resolve masks lazily by frame path or callback."""

    def __init__(self, masks: dict | Callable[[AstroImage], np.ndarray | None]):
        self.masks = masks

    def get_mask(self, astro_image: AstroImage, shape: tuple[int, int]) -> np.ndarray:
        if callable(self.masks):
            mask = self.masks(astro_image)
        else:
            mask = self.masks.get(astro_image.info.path)
        return np.ones(shape, dtype=np.float32) if mask is None else _as_mask(mask, shape)


class FileMaskProvider:
    """Load per-frame masks lazily and retain only the most recent mask."""

    def __init__(self, paths: dict[Path, Path], loader: Callable[[Path], np.ndarray]):
        self.paths = {Path(frame): Path(mask) for frame, mask in paths.items()}
        self.loader = loader
        self._cached_path: Path | None = None
        self._cached_mask: np.ndarray | None = None

    def get_mask(self, astro_image: AstroImage, shape: tuple[int, int]) -> np.ndarray:
        path = self.paths.get(astro_image.info.path)
        if path is None:
            return np.ones(shape, dtype=np.float32)
        if path != self._cached_path:
            self._cached_mask = np.asarray(self.loader(path), dtype=np.float32)
            self._cached_path = path
        return _as_mask(self._cached_mask, shape)


class CompositeMaskProvider:
    def __init__(self, providers: Iterable[WeightMaskProvider]):
        self.providers = tuple(providers)

    def get_mask(self, astro_image: AstroImage, shape: tuple[int, int]) -> np.ndarray:
        return compose_masks(
            (provider.get_mask(astro_image, shape) for provider in self.providers), shape
        )


class AlignedMaskProvider:
    """Apply each frame's star/ground alignment to its source-grid mask."""

    def __init__(
        self,
        base: WeightMaskProvider,
        transformer: ImageTransformer | None = None,
        transform_for: Callable[[AstroImage], TransformData] | None = None,
    ):
        self.base = base
        self.transformer = transformer or ImageTransformer()
        self.transform_for = transform_for

    def get_mask(self, astro_image: AstroImage, shape: tuple[int, int]) -> np.ndarray:
        mask = self.base.get_mask(astro_image, shape)
        transform = (
            self.transform_for(astro_image)
            if self.transform_for is not None
            else astro_image.info.transform
        )
        if transform is None or transform.matrix is None:
            return mask
        return self.transformer.apply_mask(mask, transform.matrix)


class AlignmentValidityMaskProvider:
    """Generate the valid transformed footprint without retaining frame masks."""

    def __init__(
        self,
        transformer: ImageTransformer | None = None,
        transform_for: Callable[[AstroImage], TransformData] | None = None,
    ):
        self.transformer = transformer or ImageTransformer()
        self.transform_for = transform_for

    def get_mask(self, astro_image: AstroImage, shape: tuple[int, int]) -> np.ndarray:
        transform = (
            self.transform_for(astro_image)
            if self.transform_for is not None
            else astro_image.info.transform
        )
        if transform is None or transform.matrix is None:
            return np.ones(shape, dtype=np.float32)
        return self.transformer.apply_mask(np.ones(shape, dtype=np.float32), transform.matrix)
