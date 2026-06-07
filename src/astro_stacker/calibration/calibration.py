"""Image calibration using master frames.

Applies calibration frames (dark, bias, flat, flat-dark) to remove
electronic noise and optical effects from light frames.
"""

from dataclasses import dataclass
import numpy as np
from pathlib import Path

from ..io.image_data import AstroImage
from ..combination.provider import FrameProvider


@dataclass
class CalibrationFrameSet:
    """Paths to calibration frame files.
    
    Attributes:
        darks: Paths to dark frames (or None)
        biases: Paths to bias frames (or None)
        flats: Paths to flat field frames (or None)
        flat_darks: Paths to dark frames for flats (or None)
    """
    darks: list[Path] | None
    biases: list[Path] | None
    flats: list[Path] | None
    flat_darks: list[Path] | None


@dataclass
class CalibrationMasterFrames:
    """Master frames for calibration (pre-combined from calibration sets).
    
    Attributes:
        dark: Master dark frame (or None)
        bias: Master bias frame (or None)
        flat: Master flat frame (or None)
        flat_dark: Master dark for flats (or None)
    """
    dark: np.ndarray | None
    bias: np.ndarray | None
    flat: np.ndarray | None
    flat_dark: np.ndarray | None


class CalibrationPipeline:
    """Configuration for which calibration frames to apply."""
    
    def __init__(
        self,
        use_darks: bool = False,
        use_biases: bool = False,
        use_flats: bool = False,
        use_flat_darks: bool = False
    ):
        """Initialize calibration pipeline.
        
        Args:
            use_darks: Apply dark frame calibration
            use_biases: Apply bias frame calibration
            use_flats: Apply flat field calibration
            use_flat_darks: Apply dark frame subtraction to flats
        """
        self.use_darks = use_darks
        self.use_biases = use_biases
        self.use_flats = use_flats
        self.use_flat_darks = use_flat_darks



class Calibrator:
    """Applies calibration frames to images.
    
    Order of operations:
    1. Subtract dark frames (removes thermal noise)
    2. Subtract bias frames (removes DC offset)
    3. Divide by flat field (corrects for vignetting, dust, etc.)
       - First subtract flat_dark from flat if enabled
    """
    
    def __init__(self, master: CalibrationMasterFrames, pipeline: CalibrationPipeline):
        """Initialize calibrator.
        
        Args:
            master: Pre-computed master calibration frames
            pipeline: Configuration for which frames to apply
        """
        self.master = master
        self.pipeline = pipeline

    def calibrate(self, image: np.ndarray) -> np.ndarray:
        """Apply calibration to an image.
        
        Args:
            image: Input image array
            
        Returns:
            Calibrated image as float32
        """
        image = image.astype(np.float32)

        if self.pipeline.use_darks and self.master.dark is not None:
            dark = self.master.dark
            image -= dark

        if self.pipeline.use_biases and self.master.bias is not None:
            bias = self.master.bias
            image -= bias

        if self.pipeline.use_flats and self.master.flat is not None:
            flat = self.master.flat
            if self.pipeline.use_flat_darks and self.master.flat_dark is not None:
                flat_dark = self.master.flat_dark
                flat -= flat_dark

            # Normalize flat to unit mean and divide
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


class CalibrationManager:
    """Manages multiple calibrators."""
    
    def __init__(self, calibrators: list[Calibrator] | None = None) -> None:
        """Initialize manager.
        
        Args:
            calibrators: List of Calibrator objects to manage
        """
        self.calibrators = calibrators or []

    def register(self, calibrator: Calibrator) -> None:
        """Add a calibrator to the list.
        
        Args:
            calibrator: Calibrator object to add
        """
        self.calibrators.append(calibrator)

    def apply_all(self, image: np.ndarray) -> CalibrationResult:
        result_image = image
        applied: list[str] = []

        for calibrator in self.calibrators:
            result_image = calibrator.calibrate(result_image)
            applied.append(type(calibrator).__name__)

        return CalibrationResult(image=result_image, applied=applied)


def sigma_clip():
    pass


class MasterFrameBuilder:
    def __init__(self, provider: FrameProvider):
        self.provider = provider

    def build(self, images: list[AstroImage], method="median") -> np.ndarray:
        stack = []

        for img in images:
            arr = self.provider.get_image(img)
            stack.append(arr)

        stack = np.stack(stack, axis=0)

        if method == "median":
            return np.median(stack, axis=0)
        elif method == "mean":
            return np.mean(stack, axis=0)
        else:
            raise ValueError("The method is an invalid value")
        
        return stack