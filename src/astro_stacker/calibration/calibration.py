"""Image calibration using master frames.

Applies calibration frames (dark, bias, flat, flat-dark) to remove
electronic noise and optical effects from light frames.
"""

from dataclasses import dataclass
import logging
import numpy as np

from ..io.image_data import AstroImage
from ..core.frame_provider import FrameProvider
from ..project.project import Project
from ..project.settings import CalibrationSettings
from ..stacking.combiner import Method, ImageCombiner

from collections.abc import Iterable

logger = logging.getLogger(__name__)


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
        calibrated = image.astype(np.float32, copy=True)

        if self.master.sub_frame is not None:
            calibrated = calibrated - self.master.sub_frame.astype(np.float32, copy=False)

        if self.master.flat is not None:
            flat = self.master.flat.astype(np.float32, copy=True)
            if self.master.flat_dark is not None and not self.settings.use_flat_darks:
                logger.debug("Flat-dark master exists but use_flat_darks is disabled")

            mean = float(np.mean(flat))
            if not np.isfinite(mean) or abs(mean) < 1e-8:
                logger.warning("Skipping flat calibration because the flat mean is zero")
            else:
                flat = flat / mean
                flat = np.where(np.abs(flat) < 1e-8, 1.0, flat)
                calibrated = calibrated / flat

        return np.clip(calibrated, 0, None).astype(np.float32, copy=False)
    

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
    raise NotImplementedError("未実装: calibration.sigma_clip は ImageCombiner 側へ統合予定です")


class MasterFrameBuilder:
    def __init__(self, provider: FrameProvider):
        self.provider = provider
        self.combiner = ImageCombiner(provider)

    def build(self, images: list[AstroImage], method: Method = "median", progress = None, is_cancelled=None, master_type=None) -> np.ndarray | None:
        if master_type is None: master_type = "スタック画像"
        img = self.combiner.combine(images, method, progress, is_cancelled, master_type)
        if img is None: return None
        return img.astype(np.float32, copy=False)
