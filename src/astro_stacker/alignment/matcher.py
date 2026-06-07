import numpy as np
import astroalign as aa

from ..stars.star_data import StarCatalog


def find_transform(
    reference: StarCatalog,
    target: StarCatalog
):
    ref_points = np.array([
        [s.x, s.y]
        for s in reference.stars
    ])

    tgt_points = np.array([
        [s.x, s.y]
        for s in target.stars
    ])

    transform, (src, dst) = aa.find_transform(
        tgt_points,
        ref_points
    )

    return transform, src, dst