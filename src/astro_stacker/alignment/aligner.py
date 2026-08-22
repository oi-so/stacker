"""Image alignment by star matching."""

import math

import numpy as np

from ..io.image_data import AlignmentData, TransformData
from ..stars.star_data import StarCatalog
from .alignment_data import AlignmentResult
from .matcher import find_transform


def transform_data_from_matrix(matrix: np.ndarray) -> TransformData:
    """Create consistent transform parameters from a 3x3 similarity matrix."""

    matrix = np.asarray(matrix, dtype=np.float64)
    scale = math.hypot(float(matrix[0, 0]), float(matrix[1, 0]))
    rotation = math.degrees(math.atan2(float(matrix[1, 0]), float(matrix[0, 0])))
    return TransformData(
        matrix=matrix,
        dx=float(matrix[0, 2]),
        dy=float(matrix[1, 2]),
        rotation=rotation,
        scale=scale,
    )


def compose_alignment_transforms(
    target_to_intermediate: TransformData,
    intermediate_to_reference: TransformData,
) -> TransformData:
    """Compose target→intermediate and intermediate→reference transforms."""

    if target_to_intermediate.matrix is None or intermediate_to_reference.matrix is None:
        raise ValueError("Cannot compose an alignment transform without a matrix")

    matrix = (
        np.asarray(intermediate_to_reference.matrix, dtype=np.float64)
        @ np.asarray(target_to_intermediate.matrix, dtype=np.float64)
    )
    return transform_data_from_matrix(matrix)


def align_catalogs(
    reference_catalog: StarCatalog,
    target_catalog: StarCatalog,
) -> AlignmentResult:
    """Align a target star catalog to a reference star catalog."""

    transform, src, dst = find_transform(reference_catalog, target_catalog)

    predicted = transform(src)
    rms = np.sqrt(np.mean(np.sum((predicted - dst) ** 2, axis=1)))

    return AlignmentResult(
        transform=transform_data_from_matrix(transform.params),
        info=AlignmentData(
            reference_star_count=len(reference_catalog.stars),
            matched_star_count=len(src),
            rms_error=float(rms),
        ),
    )
