from ..io.image_data import AstroImage, ColorMode
from ..calibration.calibration import Calibrator
from ..core.provider import FrameProvider

import numpy as np



class CalibratedFrameProvider:
    def __init__(self, base_provider: FrameProvider, calibrator: Calibrator):
        self.base_provider = base_provider
        self.calibrator = calibrator

    def get_image(self, astro_image: AstroImage) -> np.ndarray:
        image = self.base_provider.get_image(astro_image)
        image = self.calibrator.calibrate(image)
        return image