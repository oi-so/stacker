"""Apply alignment transformations to images."""

from skimage.transform import SimilarityTransform, warp
import numpy as np

from ..io.image_data import TransformData



def apply_transform(
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

    t = SimilarityTransform(
        matrix=transform.matrix
    )

    return warp(
        image,
        inverse_map=t.inverse,
        preserve_range=True
    ).astype(image.dtype)