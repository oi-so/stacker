"""Frame provider protocol for image retrieval.

Defines the interface for accessing image data in the combination pipeline.
"""

from typing import Protocol, runtime_checkable
from ..io.image_data import AstroImage
from ..io.image_manager import ImageManager
from ..calibration.calibration import Calibrator
import numpy as np


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
    



class CalibratedFrameProvider:
    def __init__(self, base_provider: FrameProvider, calibrator: Calibrator):
        self.base_provider = base_provider
        self.calibrator = calibrator

    def get_image(self, astro_image: AstroImage) -> np.ndarray:
        image = self.base_provider.get_image(astro_image)
        return self.calibrator.calibrate(image)