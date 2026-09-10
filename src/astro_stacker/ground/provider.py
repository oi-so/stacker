"""Lazy provider for independently measured ground transforms."""

from pathlib import Path

import numpy as np

from ..alignment.transform import ImageTransformer
from ..core.frame_provider import FrameProvider
from ..io.image_data import AstroImage, TransformData


class GroundAlignedFrameProvider:
    def __init__(
        self,
        base_provider: FrameProvider,
        transforms: dict[Path, np.ndarray],
        transformer: ImageTransformer | None = None,
    ):
        self.base_provider = base_provider
        self.transforms = transforms
        self.transformer = transformer or ImageTransformer()

    def get_image(self, astro_image: AstroImage) -> np.ndarray:
        image = self.base_provider.get_image(astro_image)
        matrix = self.transforms.get(astro_image.info.path)
        if matrix is None:
            raise ValueError(f"Missing ground transform for {astro_image.info.path}")
        return self.transformer.apply_transform(
            image, astro_image, TransformData(matrix=np.asarray(matrix, dtype=np.float64))
        )
