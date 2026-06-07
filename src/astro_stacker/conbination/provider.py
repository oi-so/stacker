from typing import Protocol, runtime_checkable
from ..io.image_data import AstroImage
from ..io.image_manager import ImageManager
import numpy as np


@runtime_checkable
class FrameProvider(Protocol):
    def get_image(self, astro_image: AstroImage) -> np.ndarray:
        ...


class ImageManagerProvider:
    def __init__(self, manager: ImageManager):
        self.manager = manager

    def get_image(self, astro_image: AstroImage) -> np.ndarray:
        return self.manager.get_image(astro_image)