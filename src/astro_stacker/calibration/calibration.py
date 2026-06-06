from dataclasses import dataclass
import numpy as np
from pathlib import Path

from ..io.image_data import AstroImage
from ..io.image_manager import ImageManager



@dataclass
class CalibrationFrameSet:
    darks: list[Path] | None
    biases: list[Path] | None
    flats: list[Path] | None
    flat_darks: list[Path] | None


@dataclass
class CalibrationMasterFrames:
    dark: np.ndarray | None
    bias: np.ndarray | None
    flat: np.ndarray | None
    flat_dark: np.ndarray | None


class CalibrationPipeline:
    def __init__(
        self,
        use_darks: bool = False,
        use_biases: bool = False,
        use_flats: bool = False,
        use_flat_darks: bool = False
    ):
        self.use_darks = use_darks
        self.use_biases = use_biases
        self.use_flats = use_flats
        self.use_flat_darks = use_flat_darks



class Calibrator:
    def __init__(self, master: CalibrationMasterFrames, pipeline: CalibrationPipeline):
        self.master = master
        self.pipeline = pipeline

    def calibrate(self, image: np.ndarray) -> np.ndarray:
        image = image.astype(np.float32)

        if self.pipeline.use_darks and self.master.dark:
            dark = self.master.dark
            image -= dark

        if self.pipeline.use_biases and self.master.bias:
            bias = self.master.bias
            image -= bias

        if self.pipeline.use_flats and self.master.flat:
            flat = self.master.flat
            if self.pipeline.use_flat_darks and self.master.flat_dark:
                flat_dark = self.master.dark
                flat -= flat_dark

            flat = flat / np.mean(flat)
            image /= flat

        return image
    


def sigma_clip():
    pass


class MasterFrameBuilder:
    def __init__(self, manager: ImageManager):
        self.manager = manager

    def build(self, images: list[AstroImage], method="median") -> np.ndarray:
        stack = []

        for img in images:
            arr = self.manager.get_image(img)
            stack.append(arr)

        stack = np.stack(stack, axis=0)

        if method == "median":
            return np.median(stack, axis=0)
        elif method == "mean":
            return np.mean(stack, axis=0)
        else:
            raise ValueError("The method is an invalid value")
        
        return stack