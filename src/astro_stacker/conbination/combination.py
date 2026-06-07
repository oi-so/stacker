import numpy as np
from typing import Iterable, Literal
from .provider import FrameProvider
from ..io.image_data import AstroImage


Method = Literal["mean", "median", "sigma_clip", "add"]



class ImageCombiner:
    def __init__(self, provider: FrameProvider):
        self.provider = provider

    
    def combine(
        self, 
        images: Iterable[AstroImage], 
        method: Method = "mean"
    ) -> np.ndarray:
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
        acc = None
        count = 0

        for img in images:
            arr = self.provider.get_image(img).astype(np.float32)

            if acc is None:
                acc = np.zeros_like(arr, dtype=np.float32)

            acc += arr
            count += 1

        if count == 0:
            raise ValueError("No images provided")

        return acc / count
    
    
    def _add(self, images: Iterable[AstroImage]) -> np.ndarray:
        acc = None
        count = 0

        for img in images:
            arr = self.provider.get_image(img).astype(np.float32)

            if acc is None:
                acc = np.zeros_like(arr, dtype=np.float32)

            acc += arr
            count += 1

        if count == 0:
            raise ValueError("No images provided")
        
        return acc
    
    
    def _median(self, images: Iterable[AstroImage]) -> np.ndarray:
        chunks = []
        chunk = []

        for img in images:
            arr = self.provider.get_image(img).astype(np.float32)
            chunk.append(arr)

            if len(chunk) == 50:
                chunks.append(np.median(np.stack(chunk), axis=0))
                chunk = []

        if chunk:
            chunks.append(np.median(np.stack(chunk), axis=0))

        return np.median(np.stack(chunks), axis=0)


    def _sigma_clip(self, images: Iterable[AstroImage], sigma=3.0):
        stack = []

        for img in images:
            arr = self.provider.get_image(img).astype(np.float32)
            stack.append(arr)

        stack = np.stack(stack, axis=0)

        mean = np.mean(stack, axis=0)
        std = np.std(stack, axis=0)

        mask = np.abs(stack - mean) <= sigma * std
        masked = np.where(mask, stack, np.nan)

        return np.nanmean(masked, axis=0)