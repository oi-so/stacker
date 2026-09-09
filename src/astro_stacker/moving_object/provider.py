from __future__ import annotations

import numpy as np

from ..alignment.transform import ImageTransformer
from ..core.frame_provider import FrameProvider
from ..io.image_data import AstroImage
from .transform import MovingObjectTransformBuilder


class MovingObjectAlignedFrameProvider:
    """Apply star alignment and moving-object shift in a single warp."""

    def __init__(
        self,
        base_provider: FrameProvider,
        transformer: ImageTransformer,
        transform_builder: MovingObjectTransformBuilder,
    ) -> None:
        self.base_provider = base_provider
        self.transformer = transformer
        self.transform_builder = transform_builder

    def get_image(self, astro_image: AstroImage) -> np.ndarray:
        image = self.base_provider.get_image(astro_image)
        transform = self.transform_builder.transform_for(astro_image)
        return self.transformer.apply_transform(image, astro_image, transform)
