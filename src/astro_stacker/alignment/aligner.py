from .matcher import find_transform
from ..io.image_data import TransformData, AlignmentData
from ..stars.star_data import StarCatalog
import numpy as np


def align_catalogs(
    reference_catalog: StarCatalog,
    target_catalog: StarCatalog
):
    transform, src, dst = find_transform(
        reference_catalog,
        target_catalog
    )

    matrix = transform.params

    predicted = transform(src)
    rms = np.sqrt(np.mean(np.sum((predicted - dst) ** 2, axis=1)))

    return (
        TransformData(
            matrix=transform.params,

            dx=float(transform.translation[0]),
            dy=float(transform.translation[1]),

            rotation=float(
                np.degrees(transform.rotation)
            ),

            scale=float(transform.scale)
        ),
        AlignmentData(
            reference_star_count=len(reference_catalog.stars),
            matched_star_count=len(src),
            rms_error=float(rms)
        )
    )