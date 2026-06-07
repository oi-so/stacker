from .matcher import find_transform
from ..io.image_data import TransformData, AlignmentData
from ..stars.star_data import StarCatalog


def align_catalogs(
    reference_catalog: StarCatalog,
    target_catalog: StarCatalog
):
    transform, src, dst = find_transform(
        reference_catalog,
        target_catalog
    )

    matrix = transform.params

    return (
        TransformData(
            matrix=matrix
        ),
        AlignmentData(
            reference_star_count=len(reference_catalog.stars),
            matched_star_count=len(src)
        )
    )