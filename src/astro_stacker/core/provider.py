"""Frame provider protocol for image retrieval.

Defines the interface for accessing image data in the combination pipeline.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from threading import RLock
from typing import TYPE_CHECKING

import numpy as np
from skimage.transform import SimilarityTransform

from ..alignment.transform import ImageTransformer
from ..core.debayer import debayer
from ..io.image_data import AstroImage, ColorMode, TransformData
from ..io.image_manager import ImageManager
from ..stars.star_data import Star, StarCatalog
from .frame_provider import FrameProvider

if TYPE_CHECKING:
    from ..calibration.calibration import Calibrator

@dataclass
class PreviewSettings:
    aligned: bool = True
    binning: int = 2
    debayer: bool = True
    before_binning: bool = True
    max_dimension: int = 2048



class ImageManagerProvider:
    """FrameProvider implementation using ImageManager.
    
    Wraps ImageManager to provide the FrameProvider interface.
    """
    
    def __init__(self, manager: ImageManager):
        """Initialize provider.
        
        Args:
            manager: ImageManager instance for loading images
        """
        self.manager = manager

    def cache_token(self, astro_image: AstroImage):
        return self.manager.cache_key(astro_image)

    def get_image(self, astro_image: AstroImage) -> np.ndarray:
        """Get image data using ImageManager."""
        return self.manager.get_image(astro_image)
    



class DebayerFrameProvider:
    def __init__(self, base_provider: FrameProvider):
        self.base_provider = base_provider

    def get_image(self, astro_image: AstroImage) -> np.ndarray:
        image = self.base_provider.get_image(astro_image)

        if astro_image.info.color_mode == ColorMode.BAYER:
            image = debayer(
                image,
                astro_image.info.cfa_type
            )

        return image




class CalibratedFrameProvider:
    def __init__(self, base_provider: FrameProvider, calibrator: "Calibrator"):
        self.base_provider = base_provider
        self.calibrator = calibrator

    def get_image(self, astro_image: AstroImage) -> np.ndarray:
        image = self.base_provider.get_image(astro_image)
        image = self.calibrator.calibrate(image)
        return image



class BinningFrameProvider(FrameProvider):
    def __init__(self, base_provider: FrameProvider, factor: int = 2):
        self.base_provider = base_provider
        self.factor = factor

    def get_image(self, astro_image: AstroImage) -> np.ndarray:
        image = self.base_provider.get_image(astro_image)
        h, w = image.shape[:2]
        f = self.factor

        h2 = (h // f) * f
        w2 = (w // f) * f
        image = image[:h2, :w2]

        if image.ndim == 2:
            image = image.reshape(h2 // f, f, w2 // f, f).mean(axis=(1, 3))
        else:
            c = image.shape[2]
            image = image.reshape(h2 // f, f, w2 // f, f, c).mean(axis=(1, 3))

        return image
    

@dataclass(slots=True)
class PreviewImage:
    image: np.ndarray
    scale_x: float
    scale_y: float
    all_stars: StarCatalog | None = None
    alignment_stars: StarCatalog | None = None

class PreviewProvider:
    def __init__(
        self,
        manager: ImageManager,
        transformer: ImageTransformer | None = None,
        calibrator: Calibrator | None = None,
        max_cache_bytes: int = 128 * 1024**2,
    ):
        self.manager = manager
        self.transformer = transformer
        self.calibrator = calibrator
        self.max_cache_bytes = max(0, max_cache_bytes)
        self._cache = OrderedDict()
        self._cache_bytes = 0
        self._lock = RLock()

    @staticmethod
    def _bin(image: np.ndarray, factor: int) -> np.ndarray:
        if factor <= 1:
            return image
        h, w = image.shape[:2]
        h2, w2 = (h // factor) * factor, (w // factor) * factor
        cropped = image[:h2, :w2]
        if cropped.ndim == 2:
            return cropped.reshape(h2 // factor, factor, w2 // factor, factor).mean(
                axis=(1, 3), dtype=np.float32
            )
        channels = cropped.shape[2]
        return cropped.reshape(
            h2 // factor, factor, w2 // factor, factor, channels
        ).mean(axis=(1, 3), dtype=np.float32)

    def _cache_get(self, key):
        with self._lock:
            image = self._cache.get(key)
            if image is not None:
                self._cache.move_to_end(key)
            return image

    def _cache_put(self, key, image: np.ndarray) -> None:
        if image.nbytes > self.max_cache_bytes:
            return
        with self._lock:
            old = self._cache.pop(key, None)
            if old is not None:
                self._cache_bytes -= old.nbytes
            while self._cache and self._cache_bytes + image.nbytes > self.max_cache_bytes:
                self._cache_bytes -= self._cache.popitem(last=False)[1].nbytes
            self._cache[key] = image
            self._cache_bytes += image.nbytes

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()
            self._cache_bytes = 0

    def get_image(self, astro_image: AstroImage, settings: PreviewSettings) -> PreviewImage:
        is_aligned_applied = False
        transform_matrix = None
        if self.transformer and settings.aligned and astro_image.info.is_aligned:
            is_aligned_applied = True
            transform_matrix = astro_image.info.transform.matrix
        maximum = max(256, int(settings.max_dimension))
        auto_factor = max(
            1,
            int(np.ceil(max(astro_image.info.shape.width, astro_image.info.shape.height) / maximum)),
        )
        factor = max(1, int(settings.binning), auto_factor)
        matrix_key = (
            None
            if transform_matrix is None
            else tuple(np.asarray(transform_matrix, dtype=np.float64).ravel())
        )
        key = (
            self.manager.cache_key(astro_image),
            factor,
            settings.debayer,
            settings.before_binning,
            matrix_key,
        )
        final_image = self._cache_get(key)
        if final_image is None:
            image = self.manager.get_image(astro_image)
            if settings.before_binning:
                if settings.debayer and astro_image.info.color_mode == ColorMode.BAYER:
                    image = debayer(image, astro_image.info.cfa_type)
                    image = self._bin(image, factor)
                else:
                    image = self._bin(image, factor)
            elif settings.debayer and astro_image.info.color_mode == ColorMode.BAYER:
                image = debayer(image, astro_image.info.cfa_type)
            if is_aligned_applied and transform_matrix is not None:
                matrix = np.asarray(transform_matrix, dtype=np.float64)
                if settings.before_binning and factor > 1:
                    scale = np.diag([1 / factor, 1 / factor, 1.0])
                    matrix = scale @ matrix @ np.linalg.inv(scale)
                image = self.transformer.apply_transform(
                    image, astro_image, TransformData(matrix=matrix)
                )
            if not settings.before_binning:
                image = self._bin(image, factor)
            final_image = np.asarray(image, dtype=np.float32)
            self._cache_put(key, final_image)

        if is_aligned_applied and transform_matrix is not None:
            all_stars = self._transform_catalog(astro_image.info.stars.all_stars, transform_matrix)
            alignment_stars = self._transform_catalog(astro_image.info.stars.alignment_stars, transform_matrix)
        else:
            all_stars = astro_image.info.stars.all_stars
            alignment_stars = astro_image.info.stars.alignment_stars

        return PreviewImage(
            final_image,
            scale_x=final_image.shape[1] / astro_image.info.shape.width,
            scale_y=final_image.shape[0] / astro_image.info.shape.height,
            all_stars=all_stars,
            alignment_stars=alignment_stars
        )
    
    def _transform_catalog(self, catalog: StarCatalog | None, transform_matrix: np.ndarray | None) -> StarCatalog | None:
        """星のカタログの座標をアライメント行列を使って変換するヘルパーメソッド"""
        if catalog is None:
            return None
        if transform_matrix is None:
            return catalog


        t = SimilarityTransform(matrix=transform_matrix)
        
        # すべての星の座標を抽出して一括変換
        coords = np.array([[star.x, star.y] for star in catalog.stars])
        transformed_coords = t(coords)

        new_catalog = StarCatalog([
            Star(
                x=transformed_coords[i, 0],
                y=transformed_coords[i, 1],
                flux=star.flux,
                peak=star.peak,
                sharpness=star.sharpness,
                roundness=star.roundness,
                fwhm=star.fwhm,
                ellipticity=star.ellipticity,
            )
            for i, star in enumerate(catalog.stars)
        ])
        for i, star in enumerate(new_catalog.stars):
            star.x = transformed_coords[i, 0]
            star.y = transformed_coords[i, 1]
            
        return new_catalog
