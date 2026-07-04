"""Image combination (stacking) with multiple methods.

Combines multiple aligned images using various statistical methods
to produce a high signal-to-noise ratio output image.
"""

import numpy as np
from typing import Literal
import logging
import os
import tempfile
from pathlib import Path
from ..core.frame_provider import FrameProvider
from ..io.image_data import AstroImage


Method = Literal["mean", "median", "sigma_clip", "add"]
logger = logging.getLogger(__name__)

MEMORY_LIMIT = 512 * 1024 * 1024


class ImageCombiner:
    """Combine multiple images using a chosen method.
    
    Supports:
    - mean: Simple average
    - median: Median (robust to outliers)
    - sigma_clip: Sigma clipping (rejects outliers beyond N*sigma)
    - add: Sum all images
    """
    def __init__(self, provider: FrameProvider):
        self.provider = provider

    
    def combine(
        self, 
        images: list[AstroImage], 
        method: Method = "mean",
        progress=None,
        is_cancelled=None,
        combine_msg: str = "スタック画像"
    ) -> np.ndarray | None:
        """Combine images using specified method.
        
        Args:
            images: Iterable of aligned AstroImage objects
            method: Combination method ("mean", "median", "sigma_clip", "add")
            
        Returns:
            Combined image as numpy array
            
        Raises:
            ValueError: If method is unknown or no images provided
        """
        enabled_images = [image for image in images if image.info.enabled]
        logger.info("Combining %d frames with method=%s", len(enabled_images), method)
        if method == "mean":
            return self._mean(enabled_images, progress, is_cancelled, combine_msg)
        elif method == "add":
            return self._add(enabled_images, progress, is_cancelled, combine_msg)
        elif method == "median":
            return self._median(enabled_images, progress, is_cancelled, combine_msg)
        elif method == "sigma_clip":
            return self._sigma_clip(enabled_images, progress, is_cancelled, combine_msg)
        else:
            raise ValueError(f"Unknown method: {method}")
        

    def _mean(self, images: list[AstroImage], progress=None, is_cancelled=None, combine_msg: str = "スタック画像") -> np.ndarray | None:
        """Compute mean of images. Sensitive to outliers but fast."""
        acc = None
        count = 0

        for i, img in enumerate(images, 1):
            if is_cancelled and is_cancelled(): return None
            if progress:
                progress(f"{combine_msg}生成中", i, len(images), f"{img.info.path.name}")
            logger.info("Meaning frame %d/%d: %s", i, len(images), img.info.path.name)

            arr = self.provider.get_image(img).astype(np.float32)

            if acc is None:
                acc = np.zeros_like(arr, dtype=np.float32)

            acc += arr
            count += 1

        if acc is None:
            raise ValueError("No images provided")

        return acc / count
    
    
    def _add(self, images: list[AstroImage], progress=None, is_cancelled=None, combine_msg: str = "スタック画像") -> np.ndarray | None:
        """Sum all images. Result may be very bright, use with caution."""
        acc = None
        count = 0

        for i, img in enumerate(images, 1):
            if is_cancelled and is_cancelled(): return None
            if progress:
                progress(f"{combine_msg}生成中", i, len(images), f"{img.info.path.name}")
            logger.info("Adding frame %d/%d: %s", i, len(images), img.info.path.name)
            arr = self.provider.get_image(img).astype(np.float32)

            if acc is None:
                acc = np.zeros_like(arr, dtype=np.float32)

            acc += arr
            count += 1

        if acc is None:
            raise ValueError("No images provided")
        
        return acc
    

    def _calc_row_chunk(self, shape: tuple[int, ...], dtype: np.dtype, num_images: int) -> int:
        bytes_per_pixel = np.dtype(dtype).itemsize
        bytes_per_row = num_images * shape[1] * bytes_per_pixel

        if len(shape) == 3:
            bytes_per_row *= shape[2]

        return max(1, MEMORY_LIMIT // bytes_per_row)


    def _build_memmap(
        self,
        images: list[AstroImage],
        shape,
        dtype,
        progress=None,
        is_cancelled=None,
        combine_msg="スタック画像",
        temp_dir: Path | None = None,
    ) -> tuple[np.memmap, str] | tuple[None, None]:
        
        if temp_dir is None:
            fd, tmp_filename = tempfile.mkstemp(suffix=".dat")
        else:
            temp_dir.mkdir(parents=True, exist_ok=True)
            fd, tmp_filename = tempfile.mkstemp(
                suffix=".dat",
                dir=temp_dir,
            )

        os.close(fd)

        mmap_stack = np.memmap(
            tmp_filename,
            dtype=dtype,
            mode="w+",
            shape=(len(images), *shape),
        )

        try:
            for i, img in enumerate(images):
                if is_cancelled and is_cancelled():
                    del mmap_stack
                    os.remove(tmp_filename)
                    return None, None

                if progress:
                    progress(
                        f"{combine_msg}データ準備中",
                        i + 1,
                        len(images),
                        img.info.path.name,
                    )

                logger.info(
                    "Loading frame %d/%d: %s",
                    i + 1,
                    len(images),
                    img.info.path.name,
                )

                mmap_stack[i] = self.provider.get_image(img).astype(dtype)

            mmap_stack.flush()
            del mmap_stack

            mmap_stack = np.memmap(
                tmp_filename,
                dtype=dtype,
                mode="r",
                shape=(len(images), *shape),
            )

            return mmap_stack, tmp_filename

        except Exception:
            del mmap_stack
            if os.path.exists(tmp_filename):
                os.remove(tmp_filename)
            raise
    
    def _median(
        self,
        images,
        progress=None,
        is_cancelled=None,
        combine_msg="スタック画像",
    ) -> np.ndarray | None:
        first = self.provider.get_image(images[0])

        shape = first.shape
        dtype = np.float32
        num_images = len(images)

        mmap_stack, tmp_filename = self._build_memmap(
            images,
            shape,
            dtype,
            progress,
            is_cancelled,
            combine_msg,
        )

        if mmap_stack is None:
            return None

        try:
            result = np.empty(shape, dtype=dtype)

            row_chunk = self._calc_row_chunk(shape, dtype, num_images)
            h = shape[0]
            num_chunks = (h + row_chunk - 1) // row_chunk

            logger.info(
                "Median: row_chunk=%d (%d chunks)",
                row_chunk,
                num_chunks,
            )

            for chunk_idx, y in enumerate(range(0, h, row_chunk)):
                if is_cancelled and is_cancelled():
                    return None

                if progress:
                    progress(
                        f"{combine_msg}生成中",
                        chunk_idx + 1,
                        num_chunks,
                        "メディアン計算中...",
                    )

                y_end = min(y + row_chunk, h)

                chunk = mmap_stack[:, y:y_end]

                result[y:y_end] = np.median(chunk, axis=0)

            return result

        finally:
            del mmap_stack
            if os.path.exists(tmp_filename):
                os.remove(tmp_filename)


    def _sigma_clip(
        self,
        images,
        progress=None,
        is_cancelled=None,
        combine_msg="スタック画像",
        sigma=3.0,
    ) -> np.ndarray | None:
        first = self.provider.get_image(images[0])

        shape = first.shape
        dtype = np.float32
        num_images = len(images)

        mmap_stack, tmp_filename = self._build_memmap(
            images,
            shape,
            dtype,
            progress,
            is_cancelled,
            combine_msg,
        )

        if mmap_stack is None:
            return None

        try:
            result = np.empty(shape, dtype=dtype)

            row_chunk = self._calc_row_chunk(shape, dtype, num_images)
            h = shape[0]
            num_chunks = (h + row_chunk - 1) // row_chunk

            logger.info(
                "Sigma clip: row_chunk=%d (%d chunks)",
                row_chunk,
                num_chunks,
            )

            for chunk_idx, y in enumerate(range(0, h, row_chunk)):
                if is_cancelled and is_cancelled():
                    return None

                if progress:
                    progress(
                        f"{combine_msg}生成中",
                        chunk_idx + 1,
                        num_chunks,
                        "シグマクリップ中...",
                    )

                y_end = min(y + row_chunk, h)

                chunk = np.array(
                    mmap_stack[:, y:y_end],
                    copy=True,
                )

                mean = np.mean(chunk, axis=0)
                std = np.std(chunk, axis=0)

                chunk[np.abs(chunk - mean) > sigma * std] = np.nan

                result[y:y_end] = np.nanmean(chunk, axis=0)

            return result

        finally:
            del mmap_stack
            if os.path.exists(tmp_filename):
                os.remove(tmp_filename)