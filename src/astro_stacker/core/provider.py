"""Frame provider protocol for image retrieval.

Defines the interface for accessing image data in the combination pipeline.
"""

from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from skimage.transform import SimilarityTransform

from ..io.image_data import AstroImage, ColorMode
from ..io.image_manager import ImageManager
from ..core.debayer import debayer
from ..alignment.transform import ImageTransformer, AlignedFrameProvider
from .frame_provider import FrameProvider
from ..stars.star_data import StarCatalog, Star


from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ..calibration.calibration import Calibrator

@dataclass
class PreviewSettings:
    aligned: bool = True
    binning: int = 2
    debayer: bool = True
    before_binning: bool = True



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
    def __init__(self, manager: ImageManager, transformer: ImageTransformer | None = None, calibrator: Calibrator | None = None):
        self.manager = manager
        self.transformer = transformer
        self.calibrator = calibrator

    def get_image(self, astro_image: AstroImage, settings: PreviewSettings) -> PreviewImage:
        provider: FrameProvider = ImageManagerProvider(self.manager)
        is_aligned_applied = False
        transform_matrix = None

        if (
            self.transformer and settings.aligned
            and astro_image.info.is_aligned
        ):
            provider = AlignedFrameProvider(
                provider,
                self.transformer
            )
            is_aligned_applied = True
            transform_matrix = astro_image.info.transform.matrix

        if settings.before_binning:
            if settings.binning != 1:
                provider = BinningFrameProvider(provider, settings.binning)


        if settings.debayer:
            provider = DebayerFrameProvider(provider)

        if not settings.before_binning:
            provider = BinningFrameProvider(provider, settings.binning)

        final_image = provider.get_image(astro_image)

        if is_aligned_applied and transform_matrix is not None:
            all_stars = self._transform_catalog(astro_image.info.stars.all_stars, transform_matrix)
            alignment_stars = self._transform_catalog(astro_image.info.stars.alignment_stars, transform_matrix)
        else:
            all_stars = astro_image.info.stars.all_stars
            alignment_stars = astro_image.info.stars.alignment_stars

        return PreviewImage(
            final_image,
            scale_x = 1 / settings.binning,
            scale_y = 1 / settings.binning,
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