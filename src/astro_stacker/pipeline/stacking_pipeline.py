from typing import Iterable

import numpy as np

from ..alignment.aligner import align_catalogs
from ..alignment.transform import AlignedFrameProvider, ImageTransformer
from ..core.provider import ImageManagerProvider
from ..io.image_data import AstroImage
from ..io.image_manager import ImageManager
from ..stacking.combiner import ImageCombiner, Method
from ..stars.detector import detect_stars


class StackingPipeline:

    def __init__(
        self,
        manager: ImageManager,
    ):
        self.manager = manager

    def run(
        self,
        images: list[AstroImage],
        method: Method = "mean",
    ) -> np.ndarray:

        if len(images) == 0:
            raise ValueError(
                "No images provided"
            )

        provider = ImageManagerProvider(
            self.manager
        )

        reference = provider.get_image(
            images[0]
        )

        reference_catalog = detect_stars(
            reference
        )

        for image in images[1:]:

            target = provider.get_image(
                image
            )

            target_catalog = detect_stars(
                target
            )

            result = align_catalogs(
                reference_catalog,
                target_catalog
            )

            image.info.transform = (
                result.transform
            )

            image.info.alignment_data = (
                result.info
            )

        aligned_provider = (
            AlignedFrameProvider(
                provider,
                ImageTransformer()
            )
        )

        combiner = ImageCombiner(
            aligned_provider
        )

        return combiner.combine(
            images,
            method
        )