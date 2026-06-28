"""Image combination (stacking) with multiple methods.

Combines multiple aligned images using various statistical methods
to produce a high signal-to-noise ratio output image.
"""

import numpy as np
from typing import Iterable, Literal
import logging
from ..core.frame_provider import FrameProvider
from ..io.image_data import AstroImage


Method = Literal["mean", "median", "sigma_clip", "add"]
logger = logging.getLogger(__name__)



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
            return self._median(enabled_images)
        elif method == "sigma_clip":
            return self._sigma_clip(enabled_images)
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
    
    
    # Future: process large datasets in tiles to reduce memory use.
    def _median(
        self,
        images: list[AstroImage],
        progress=None,
        is_cancelled=None, 
        combine_msg: str = "スタック画像"
    ) -> np.ndarray:

        stack = []
        if progress:
            progress(f"{combine_msg}生成中", 0, 1, "画像読み込み中...")


        for i, img in enumerate(images):
            stack.append(
                self.provider.get_image(
                    img
                ).astype(np.float32)
            )
            logger.info("Loading frame %d", img.info.path.name)

        if len(stack) == 0:
            raise ValueError(
                "No images provided"
            )

        logger.info("Taking the median...")
        return np.median(
            np.stack(stack),
            axis=0
        )


    # Future: process large datasets in tiles to reduce memory use.
    def _sigma_clip(self, images: list[AstroImage], sigma=3.0, progress=None, is_cancelled=None, combine_msg: str = "スタック画像"):
        """Sigma clipping: reject pixels more than sigma*std from mean.
        
        Robust to cosmic rays and outliers, but computationally expensive.
        """
        stack = []

        for img in images:
            arr = self.provider.get_image(img).astype(np.float32)
            stack.append(arr)
            logger.info("Loading frame %d", img.info.path.name)

        if len(stack) == 0: 
            raise ValueError("No images provided")
        
        logger.info("Stacking frames")

        stack = np.stack(stack, axis=0)

        logger.info("Meaning frames")
        mean = np.mean(stack, axis=0)
        std = np.std(stack, axis=0)

        logger.info("Clipping frames")
        mask = np.abs(stack - mean) <= sigma * std
        masked = np.where(mask, stack, np.nan)

        return np.nanmean(masked, axis=0)
