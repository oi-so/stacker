"""Apply alignment transformations to images."""

from skimage.transform import SimilarityTransform, warp
import numpy as np

from ..io.image_data import TransformData, AstroImage
from ..core.provider import FrameProvider



class ImageTransformer:
    def apply_transform(
        self,
        image: np.ndarray,
        transform: TransformData
    ) -> np.ndarray:
        """Apply pre-computed transformation to an image.
        
        Args:
            image: Input image array
            transform: TransformData containing transformation matrix
            
        Returns:
            Transformed image with same dtype as input
        """

        if transform.matrix is None:
            return image.astype(np.float32, copy=False)

        t = SimilarityTransform(matrix=transform.matrix)

        return warp(
            image,
            inverse_map=t.inverse,
            preserve_range=True
        ).astype(np.float32)



class AlignedFrameProvider:
    def __init__(self, base_provider: FrameProvider, transformer: ImageTransformer) -> None:
        self.base_provider = base_provider
        self.transformer = transformer

    
    def get_image(self, astro_image: AstroImage) -> np.ndarray:
        image = self.base_provider.get_image(astro_image)

        if astro_image.info.transform is None:
            return image
        
        return self.transformer.apply_transform(image, astro_image.info.transform)
