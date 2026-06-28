from typing import Protocol, runtime_checkable
import numpy as np
from ..io.image_data import AstroImage


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