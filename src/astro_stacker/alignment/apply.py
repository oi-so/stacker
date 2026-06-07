from skimage.transform import SimilarityTransform, warp
import numpy as np

from ..io.image_data import TransformData



def apply_transform(
    image: np.ndarray,
    transform: TransformData
) -> np.ndarray:

    t = SimilarityTransform(
        matrix=transform.matrix
    )

    return warp(
        image,
        inverse_map=t.inverse,
        preserve_range=True
    ).astype(image.dtype)