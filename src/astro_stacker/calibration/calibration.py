"""Image calibration using master frames.

Applies calibration frames (dark, bias, flat, flat-dark) to remove
electronic noise and optical effects from light frames.
"""

from dataclasses import dataclass
import numpy as np

from ..io.image_data import AstroImage
from ..core.provider import FrameProvider
from ..project.project import Project
from ..project.settings import CalibrationSettings
from ..stacking.combiner import Method, ImageCombiner

from collections.abc import Iterable


class Calibrator:
    """Applies calibration frames to images.
    
    Order of operations:
    1. Subtract dark frames (removes thermal noise)
    2. Subtract bias frames (removes DC offset)
    3. Divide by flat field (corrects for vignetting, dust, etc.)
        - First subtract flat_dark from flat if enabled
    """
    
    def __init__(self, project: Project, settings: CalibrationSettings):
        """Initialize calibrator.
        
        Args:
            project: Project class
            pipeline: Configuration for which frames to apply
        """
        self.project = project
        self.master = project.master_calibration_frames
        self.settings = settings


    def calibrate(self, image: np.ndarray) -> np.ndarray:
        """Apply calibration to an image.
        
        Args:
            image: Input image array
            
        Returns:
            Calibrated image as float32
        """
        image = image.astype(np.float32)

        if self.master.sub_frame is not None:
            image -= self.master.sub_frame

        if self.master.flat is not None:
            flat = self.master.flat.copy()
            flat = flat / np.mean(flat)
            image /= flat

        return image
    

@dataclass
class CalibrationResult:
    """Result of calibration.
    
    Attributes:
        image: Calibrated image
        applied: List of calibration types applied (e.g., ['dark', 'flat'])
    """
    image: np.ndarray
    applied: list[str]



def sigma_clip():
    pass


class MasterFrameBuilder:
    def __init__(self, provider: FrameProvider):
        self.provider = provider
        self.combiner = ImageCombiner(provider)

    def build(self, images: Iterable[AstroImage], method: Method = "median") -> np.ndarray:
        return self.combiner.combine(images, method)