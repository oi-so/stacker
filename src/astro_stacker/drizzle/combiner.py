"""Streaming square-kernel drizzle reconstruction."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import cv2
import numpy as np
import psutil

from ..core.frame_provider import FrameProvider
from ..io.image_data import AstroImage, TransformData
from ..masks.weights import WeightMaskProvider
from ..project.settings import StackingMethod


class DrizzleCombiner:
    """Map source pixels directly to a larger reference grid without pre-warping."""

    def __init__(self, provider: FrameProvider, *, chunk_rows: int = 256):
        self.provider = provider
        self.chunk_rows = max(1, int(chunk_rows))
        self.last_valid_mask: np.ndarray | None = None

    @staticmethod
    def _frame_weight(frame: AstroImage, frame_weights: dict[Path, float] | None) -> float:
        value = 1.0 if frame_weights is None else float(frame_weights.get(frame.info.path, 1.0))
        if not np.isfinite(value) or value < 0:
            raise ValueError(f"Invalid frame weight for {frame.info.path}: {value}")
        return value

    @staticmethod
    def _remap(array: np.ndarray, map_x: np.ndarray, map_y: np.ndarray) -> np.ndarray:
        result = cv2.remap(
            np.asarray(array, dtype=np.float32),
            map_x,
            map_y,
            cv2.INTER_NEAREST,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=0,
        )
        if array.ndim == 3 and array.shape[-1] == 1 and result.ndim == 2:
            result = result[..., np.newaxis]
        return result

    def combine(
        self,
        frames: list[AstroImage],
        *,
        scale: int = 2,
        pixfrac: float = 0.8,
        method: StackingMethod = StackingMethod.AVERAGE,
        mask_provider: WeightMaskProvider | None = None,
        frame_weights: dict[Path, float] | None = None,
        progress=None,
        is_cancelled=None,
        transform_for: Callable[[AstroImage], TransformData] | None = None,
    ) -> np.ndarray | None:
        frames = [frame for frame in frames if frame.info.enabled]
        if not frames:
            raise ValueError("No enabled images provided")
        if scale not in (2, 3):
            raise ValueError("Drizzle scale must be 2 or 3")
        if not np.isfinite(pixfrac) or not 0.1 <= pixfrac <= 1.0:
            raise ValueError("Drizzle pixfrac must be between 0.1 and 1.0")
        method = StackingMethod(method)
        if method not in (StackingMethod.AVERAGE, StackingMethod.ADD):
            raise ValueError("Drizzle currently supports Average and Add stacking")

        first = np.asarray(self.provider.get_image(frames[0]), dtype=np.float32)
        if first.ndim not in (2, 3) or any(size <= 0 for size in first.shape):
            raise ValueError(f"Unsupported image shape: {first.shape}")
        height, width = first.shape[:2]
        output_shape = (height * scale, width * scale, *first.shape[2:])
        required_bytes = (
            int(np.prod(output_shape, dtype=np.int64))
            + int(np.prod(output_shape[:2], dtype=np.int64))
        ) * np.dtype(np.float32).itemsize
        available = psutil.virtual_memory().available
        if required_bytes > available // 2:
            raise ValueError(
                f"Drizzle出力に最低約{required_bytes / 1024**3:.2f} GiB必要です。"
                "倍率を下げるか、ほかのアプリを終了してください。"
            )
        accumulated = np.zeros(output_shape, dtype=np.float32)
        weights = np.zeros(output_shape[:2], dtype=np.float32)

        for index, frame in enumerate(frames):
            if is_cancelled and is_cancelled():
                return None
            image = first if index == 0 else np.asarray(self.provider.get_image(frame), dtype=np.float32)
            if image.shape != first.shape:
                raise ValueError("All drizzle frames must have the same shape")
            source_mask = (
                np.ones((height, width), dtype=np.float32)
                if mask_provider is None
                else mask_provider.get_mask(frame, (height, width))
            )
            transform = transform_for(frame) if transform_for is not None else frame.info.transform
            matrix = transform.matrix
            if matrix is None:
                matrix = np.eye(3, dtype=np.float64)
            inverse = np.linalg.inv(np.asarray(matrix, dtype=np.float64))
            scalar_weight = self._frame_weight(frame, frame_weights)

            for y0 in range(0, height * scale, self.chunk_rows):
                if is_cancelled and is_cancelled():
                    return None
                y1 = min(height * scale, y0 + self.chunk_rows)
                output_y, output_x = np.mgrid[y0:y1, : width * scale]
                # Preserve pixel-centre coordinates when changing grid scale.
                reference_x = (output_x.astype(np.float64) + 0.5) / scale - 0.5
                reference_y = (output_y.astype(np.float64) + 0.5) / scale - 0.5
                denominator = (
                    inverse[2, 0] * reference_x
                    + inverse[2, 1] * reference_y
                    + inverse[2, 2]
                )
                valid_denominator = np.abs(denominator) > 1e-12
                source_x = np.divide(
                    inverse[0, 0] * reference_x
                    + inverse[0, 1] * reference_y
                    + inverse[0, 2],
                    denominator,
                    out=np.full_like(reference_x, -1),
                    where=valid_denominator,
                )
                source_y = np.divide(
                    inverse[1, 0] * reference_x
                    + inverse[1, 1] * reference_y
                    + inverse[1, 2],
                    denominator,
                    out=np.full_like(reference_y, -1),
                    where=valid_denominator,
                )
                drop = (
                    (np.abs(source_x - np.rint(source_x)) <= pixfrac / 2)
                    & (np.abs(source_y - np.rint(source_y)) <= pixfrac / 2)
                    & (source_x >= -0.5)
                    & (source_x < width - 0.5)
                    & (source_y >= -0.5)
                    & (source_y < height - 0.5)
                    & valid_denominator
                )
                map_x = source_x.astype(np.float32)
                map_y = source_y.astype(np.float32)
                sampled = self._remap(image, map_x, map_y)
                sampled_mask = self._remap(source_mask, map_x, map_y)
                pixel_weight = sampled_mask * drop.astype(np.float32) * scalar_weight
                broadcast = pixel_weight[..., np.newaxis] if sampled.ndim == 3 else pixel_weight
                accumulated[y0:y1] += sampled * broadcast
                weights[y0:y1] += pixel_weight
            if progress:
                progress("Drizzle再構成中", index + 1, len(frames), frame.info.path.name)

        if method == StackingMethod.AVERAGE:
            denominator = weights[..., np.newaxis] if accumulated.ndim == 3 else weights
            np.divide(accumulated, denominator, out=accumulated, where=denominator > 0)
        self.last_valid_mask = (weights > 0).astype(np.float32)
        invalid = weights <= 0
        if accumulated.ndim == 3:
            invalid = invalid[..., np.newaxis]
        np.copyto(accumulated, 0, where=invalid)
        return accumulated
