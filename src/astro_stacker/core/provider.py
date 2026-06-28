"""Frame provider protocol for image retrieval.

Defines the interface for accessing image data in the combination pipeline.
"""

from __future__ import annotations
from dataclasses import dataclass
import numpy as np

from ..io.image_data import AstroImage, ColorMode
from ..io.image_manager import ImageManager
from ..core.debayer import debayer
from ..alignment.transform import ImageTransformer, AlignedFrameProvider
from .frame_provider import FrameProvider


from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ..calibration.calibration import Calibrator

@dataclass
class PreviewSettings:
    aligned: bool = False
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

class PreviewProvider:
    def __init__(self, manager: ImageManager, transformer: ImageTransformer | None = None, calibrator: Calibrator | None = None):
        self.manager = manager
        self.transformer = transformer
        self.calibrator = calibrator

    def get_image(self, astro_image: AstroImage, settings: PreviewSettings) -> PreviewImage:
        provider: FrameProvider = ImageManagerProvider(self.manager)

        if settings.before_binning:
            if settings.binning != 1:
                provider = BinningFrameProvider(provider, settings.binning)

        if self.transformer and settings.aligned:
            provider = AlignedFrameProvider(
                provider,
                self.transformer
            )

        if settings.debayer:
            provider = DebayerFrameProvider(provider)

        if not settings.before_binning:
            provider = BinningFrameProvider(provider, settings.binning)

        return PreviewImage(
            provider.get_image(astro_image),
            scale_x = 1 / settings.binning,
            scale_y = 1 / settings.binning,
        )