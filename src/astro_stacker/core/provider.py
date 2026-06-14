"""Frame provider protocol for image retrieval.

Defines the interface for accessing image data in the combination pipeline.
"""

from typing import Protocol, runtime_checkable
from ..io.image_data import AstroImage, ColorMode, CFAType
from ..io.image_manager import ImageManager
import numpy as np
from ..core.debayer import debayer


@runtime_checkable
class FrameProvider(Protocol):
    """Protocol for getting image data.
    
    Implementations must provide a get_image method that returns
    pixel data for a given AstroImage.
    """
    
    def get_image(self, astro_image: AstroImage) -> np.ndarray:
        """Get image pixel data.
        
        Args:
            astro_image: AstroImage object
            
        Returns:
            Pixel data as numpy array
        """
        ...


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





