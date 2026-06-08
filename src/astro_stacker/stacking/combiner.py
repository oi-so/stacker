"""Image combination (stacking) with multiple methods.

Combines multiple aligned images using various statistical methods
to produce a high signal-to-noise ratio output image.
"""

import numpy as np
from typing import Iterable, Literal
from ..core.provider import FrameProvider
from ..io.image_data import AstroImage


Method = Literal["mean", "median", "sigma_clip", "add"]



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
        images: Iterable[AstroImage], 
        method: Method = "mean"
    ) -> np.ndarray:
        """Combine images using specified method.
        
        Args:
            images: Iterable of aligned AstroImage objects
            method: Combination method ("mean", "median", "sigma_clip", "add")
            
        Returns:
            Combined image as numpy array
            
        Raises:
            ValueError: If method is unknown or no images provided
        """
        if method == "mean":
            return self._mean(images)
        elif method == "add":
            return self._add(images)
        elif method == "median":
            return self._median(images)
        elif method == "sigma_clip":
            return self._sigma_clip(images)
        else:
            raise ValueError(f"Unknown method: {method}")
        

    def _mean(self, images: Iterable[AstroImage]) -> np.ndarray:
        """Compute mean of images. Sensitive to outliers but fast."""
        acc = None
        count = 0

        for img in images:
            arr = self.provider.get_image(img).astype(np.float32)

            if acc is None:
                acc = np.zeros_like(arr, dtype=np.float32)

            acc += arr
            count += 1

        if acc is None:
            raise ValueError("No images provided")

        return acc / count
    
    
    def _add(self, images: Iterable[AstroImage]) -> np.ndarray:
        """Sum all images. Result may be very bright, use with caution."""
        acc = None
        count = 0

        for img in images:
            arr = self.provider.get_image(img).astype(np.float32)

            if acc is None:
                acc = np.zeros_like(arr, dtype=np.float32)

            acc += arr
            count += 1

        if acc is None:
            raise ValueError("No images provided")
        
        return acc
    
    
    # TODO: 軽量化する
    def _median(
        self,
        images: Iterable[AstroImage]
    ) -> np.ndarray:

        stack = []

        for img in images:
            stack.append(
                self.provider.get_image(
                    img
                ).astype(np.float32)
            )

        if len(stack) == 0:
            raise ValueError(
                "No images provided"
            )

        return np.median(
            np.stack(stack),
            axis=0
        )


    # TODO:軽量化する
    def _sigma_clip(self, images: Iterable[AstroImage], sigma=3.0):
        """Sigma clipping: reject pixels more than sigma*std from mean.
        
        Robust to cosmic rays and outliers, but computationally expensive.
        """
        stack = []

        for img in images:
            arr = self.provider.get_image(img).astype(np.float32)
            stack.append(arr)

        if len(stack) == 0: 
            raise ValueError("No images provided")

        stack = np.stack(stack, axis=0)

        mean = np.mean(stack, axis=0)
        std = np.std(stack, axis=0)

        mask = np.abs(stack - mean) <= sigma * std
        masked = np.where(mask, stack, np.nan)

        return np.nanmean(masked, axis=0)