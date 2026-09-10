"""Streaming combinations and bounded RAM/disk statistical stacking."""

import logging
import os
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path

import numpy as np
import psutil

from ..core.frame_provider import FrameProvider
from ..core.resources import (
    DISK_RESERVE_BYTES,
    STACK_DISK_BYTES,
    STACK_MEMORY_BYTES,
)
from ..io.image_data import AstroImage
from ..masks.weights import WeightMaskProvider, validity_mask
from ..project.settings import StackingMethod, StackingSettings

logger = logging.getLogger(__name__)


class ImageCombiner:
    def __init__(
        self,
        provider: FrameProvider,
        memory_limit: int = STACK_MEMORY_BYTES,
        disk_limit: int = STACK_DISK_BYTES,
        disk_reserve: int = DISK_RESERVE_BYTES,
        temp_dir: Path | None = None,
    ):
        self.provider = provider
        self.memory_limit = max(1, memory_limit)
        self.disk_limit = max(0, disk_limit)
        self.disk_reserve = max(0, disk_reserve)
        self.temp_dir = temp_dir
        self.last_valid_mask: np.ndarray | None = None

    def combine(
        self,
        images: list[AstroImage],
        method: StackingMethod = StackingMethod.AVERAGE,
        settings: StackingSettings | None = None,
        progress=None,
        is_cancelled=None,
        combine_msg: str = "スタック画像",
        mask_provider: WeightMaskProvider | None = None,
        frame_weights: dict[Path, float] | None = None,
        invalid_fill: float = 0.0,
    ) -> np.ndarray | None:
        images = [image for image in images if image.info.enabled]
        if not images:
            raise ValueError("No enabled images provided")
        method = StackingMethod(method)
        if method == StackingMethod.MINMAX_MEAN and len(images) < 3:
            raise ValueError("最大・最小除外平均には3枚以上の画像が必要です。")
        settings = settings or StackingSettings()
        if method == StackingMethod.SIGMA_CLIP and (
            not np.isfinite(settings.sigma) or settings.sigma <= 0 or settings.iterations < 1
        ):
            raise ValueError("Sigma must be positive and iterations must be at least one")
        if is_cancelled and is_cancelled():
            return None
        logger.info("Combining %d frames with %s", len(images), method)
        if method == StackingMethod.MINMAX_MEAN and (
            mask_provider is not None or frame_weights is not None
        ):
            raise ValueError("Weighted min/max reject is not supported; use Average or Sigma Clipping")
        if method in (StackingMethod.MEDIAN, StackingMethod.SIGMA_CLIP):
            return self._statistical(
                images, method, settings, progress, is_cancelled, combine_msg,
                mask_provider, frame_weights, invalid_fill,
            )
        return self._stream(
            images, method, progress, is_cancelled, combine_msg,
            mask_provider, frame_weights, invalid_fill,
        )

    @staticmethod
    def _frame_weight(frame, frame_weights):
        if frame_weights is None:
            return 1.0
        value = float(frame_weights.get(frame.info.path, 1.0))
        if not np.isfinite(value) or value < 0:
            raise ValueError(f"Invalid frame weight for {frame.info.path}: {value}")
        return value

    @staticmethod
    def _pixel_weight(frame, arr, mask_provider, frame_weights):
        weight = validity_mask(arr)
        if mask_provider is not None:
            weight *= mask_provider.get_mask(frame, arr.shape[:2])
        weight *= ImageCombiner._frame_weight(frame, frame_weights)
        return weight

    @staticmethod
    def _broadcast_weight(weight, arr):
        return weight[..., np.newaxis] if arr.ndim == 3 else weight

    def _stream(
        self, images, method, progress, is_cancelled, message,
        mask_provider, frame_weights, invalid_fill,
    ):
        acc = low = high = weight_sum = None
        for i, frame in enumerate(images, 1):
            if is_cancelled and is_cancelled():
                return None
            if progress:
                progress(f"{message}生成中", i, len(images), frame.info.path.name)
            arr = np.asarray(self.provider.get_image(frame), dtype=np.float32)
            pixel_weight = self._pixel_weight(frame, arr, mask_provider, frame_weights)
            broadcast = self._broadcast_weight(pixel_weight, arr)
            if acc is None:
                missing = (
                    -np.inf if method == StackingMethod.MAXIMUM
                    else np.inf if method == StackingMethod.MINIMUM
                    else 0
                )
                acc = np.where(broadcast > 0, arr, missing).astype(np.float32)
                if method in (StackingMethod.AVERAGE, StackingMethod.ADD):
                    acc *= broadcast
                weight_sum = pixel_weight.copy()
                if method == StackingMethod.MINMAX_MEAN:
                    low = np.where(broadcast > 0, arr, np.inf).astype(np.float32)
                    high = np.where(broadcast > 0, arr, -np.inf).astype(np.float32)
                continue
            if arr.shape != acc.shape:
                raise ValueError("All stacking frames must have the same shape")
            if method == StackingMethod.MAXIMUM:
                np.maximum(acc, arr, out=acc, where=broadcast > 0)
            elif method == StackingMethod.MINIMUM:
                np.minimum(acc, arr, out=acc, where=broadcast > 0)
            else:
                acc += (
                    np.where(broadcast > 0, arr * broadcast, 0)
                    if method in (StackingMethod.AVERAGE, StackingMethod.ADD)
                    else arr
                )
                if method == StackingMethod.MINMAX_MEAN:
                    np.minimum(low, arr, out=low, where=broadcast > 0)
                    np.maximum(high, arr, out=high, where=broadcast > 0)
            weight_sum += pixel_weight
        if method == StackingMethod.AVERAGE:
            denominator = self._broadcast_weight(weight_sum, acc)
            np.divide(acc, denominator, out=acc, where=denominator > 0)
        elif method == StackingMethod.MINMAX_MEAN:
            acc -= low
            acc -= high
            acc /= len(images) - 2
        self.last_valid_mask = (weight_sum > 0).astype(np.float32)
        invalid = ~self.last_valid_mask.astype(bool)
        if acc.ndim == 3:
            invalid = invalid[..., np.newaxis]
        np.copyto(acc, invalid_fill, where=invalid)
        return acc

    @contextmanager
    def _storage(self, shape, budget):
        size = int(np.prod(shape, dtype=np.int64)) * np.dtype(np.float32).itemsize
        if size <= budget // 2:
            # Leave at least half the budget for reduction temporaries.
            yield np.empty(shape, dtype=np.float32)
            return
        directory = Path(self.temp_dir or tempfile.gettempdir())
        directory.mkdir(parents=True, exist_ok=True)
        if size > self.disk_limit or shutil.disk_usage(directory).free - size < self.disk_reserve:
            raise ValueError(
                f"スタック一時領域に {size / 1024**3:.2f} GiB 必要です。"
                f"上限 {self.disk_limit / 1024**3:.1f} GiB、"
                f"空き容量 {self.disk_reserve / 1024**3:.1f} GiB を確保する設定です。"
                "画像枚数を減らすか、Average / Add / 比較明 / 比較暗 / 最大・最小除外平均を選んでください。"
            )
        fd, filename = tempfile.mkstemp(prefix="astro-stacker-stack-", suffix=".dat", dir=directory)
        os.close(fd)
        stack = None
        try:
            stack = np.memmap(filename, dtype=np.float32, mode="w+", shape=shape)
            yield stack
        finally:
            if stack is not None:
                # Explicitly close the mapping before unlinking (Windows).
                stack._mmap.close()
            os.unlink(filename)

    def _statistical(
        self, images, method, settings, progress, is_cancelled, message,
        mask_provider, frame_weights, invalid_fill,
    ):
        first = np.asarray(self.provider.get_image(images[0]), dtype=np.float32)
        shape = first.shape
        if first.ndim not in (2, 3) or any(size == 0 for size in shape):
            raise ValueError(f"Unsupported image shape: {shape}")
        budget = max(1, min(self.memory_limit, psutil.virtual_memory().available // 4))
        with self._storage((len(images), *shape), budget) as stack:
            for i, frame in enumerate(images):
                if is_cancelled and is_cancelled():
                    return None
                arr = (
                    first
                    if i == 0
                    else np.asarray(self.provider.get_image(frame), dtype=np.float32)
                )
                if arr.shape != shape:
                    raise ValueError("All stacking frames must have the same shape")
                weight = self._pixel_weight(frame, arr, mask_provider, frame_weights)
                broadcast = self._broadcast_weight(weight, arr)
                stack[i] = np.where(broadcast > 0, arr, np.nan)
                if i == 0:
                    first = None
                if progress:
                    progress(f"{message}データ準備中", i + 1, len(images), frame.info.path.name)
            del arr
            result = np.empty(shape, dtype=np.float32)
            # nanstd/rejection allocate masks and full-size intermediates;
            # reserve 8x the input chunk, rather than just counting input bytes.
            row_bytes = len(images) * int(np.prod(shape[1:])) * 4
            working_budget = budget if isinstance(stack, np.memmap) else budget - stack.nbytes
            rows = max(1, min(shape[0], working_budget // max(1, row_bytes * 8)))
            chunks = (shape[0] + rows - 1) // rows
            for i, y in enumerate(range(0, shape[0], rows)):
                if is_cancelled and is_cancelled():
                    return None
                end = min(shape[0], y + rows)
                chunk = np.array(stack[:, y:end], copy=True)
                if method == StackingMethod.MEDIAN:
                    result[y:end] = np.median(chunk, axis=0, overwrite_input=True)
                else:
                    for _ in range(settings.iterations):
                        if is_cancelled and is_cancelled():
                            return None
                        mean = np.nanmean(chunk, axis=0)
                        std = np.nanstd(chunk, axis=0)
                        std[std < 1e-8] = 1.0
                        reject = np.abs(chunk - mean) > settings.sigma * std
                        if not np.any(reject):
                            break
                        # Keep the previous population when every sample would
                        # be rejected (e.g. two samples at very small sigma).
                        reject &= ~np.all(reject | np.isnan(chunk), axis=0)
                        chunk[reject] = np.nan
                    if frame_weights is None:
                        result[y:end] = np.nanmean(chunk, axis=0)
                    else:
                        scalars = np.asarray(
                            [self._frame_weight(frame, frame_weights) for frame in images],
                            dtype=np.float32,
                        ).reshape((-1,) + (1,) * (chunk.ndim - 1))
                        valid = np.isfinite(chunk)
                        numerator = np.nansum(chunk * scalars, axis=0)
                        denominator = np.sum(valid * scalars, axis=0)
                        result[y:end] = np.divide(
                            numerator, denominator,
                            out=np.full_like(numerator, np.nan), where=denominator > 0,
                        )
                if progress:
                    progress(f"{message}生成中", i + 1, chunks, method.show_name)
            valid = np.isfinite(result)
            if result.ndim == 3:
                valid_pixels = np.all(valid, axis=-1)
            else:
                valid_pixels = valid
            self.last_valid_mask = valid_pixels.astype(np.float32)
            return np.nan_to_num(result, nan=invalid_fill, posinf=invalid_fill, neginf=invalid_fill)
