"""Image alignment by star matching.

Aligns two images by finding and matching stars in both images,
then computing the transformation (translation, rotation, scale).
"""

from .matcher import find_transform
from ..io.image_data import TransformData, AlignmentData
from ..stars.star_data import StarCatalog
from .alignment_data import AlignmentResult
import numpy as np


def align_catalogs(
    reference_catalog: StarCatalog,
    target_catalog: StarCatalog
) -> AlignmentResult:
    """Align target image to reference image using star catalogs.
    
    Args:
        reference_catalog: Stars detected in reference image
        target_catalog: Stars detected in target image
        
    Returns:
        AlignmentResult with transformation and alignment metrics
    """
    transform, src, dst = find_transform(
        reference_catalog,
        target_catalog
    )

    matrix = transform.params

    predicted = transform(src)
    rms = np.sqrt(np.mean(np.sum((predicted - dst) ** 2, axis=1)))

    return AlignmentResult(
        transform=TransformData(
            matrix=matrix,

            dx=float(transform.translation[0]),
            dy=float(transform.translation[1]),

            rotation=float(
                np.degrees(
                    transform.rotation
                )
            ),

            scale=float(transform.scale)
        ),

        info=AlignmentData(
            reference_star_count=len(
                reference_catalog.stars
            ),

            matched_star_count=len(src),

            rms_error=float(rms)
        )
    )