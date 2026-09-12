"""Star matching and transformation calculation.

Matches stars between two catalogs and computes the transformation
using the astroalign library.
"""

import astroalign as aa
import numpy as np

from ..stars.star_data import StarCatalog


def find_transform(
    reference: StarCatalog,
    target: StarCatalog
):
    """Find transformation from target coordinates to reference coordinates.

    Args:
        reference: Reference star catalog
        target: Target star catalog to match
        
    Returns:
        Tuple of (transform, src, dst) where:
        - transform: astroalign SimilarityTransform object
        - src: Matched source coordinates
        - dst: Matched destination coordinates
    """
    ref_points = np.array([[s.x, s.y] for s in reference.stars])
    tgt_points = np.array([[s.x, s.y] for s in target.stars])

    if len(ref_points) < 3 or len(tgt_points) < 3:
        raise ValueError("At least three stars are required for alignment")

    max_control_points = max(len(ref_points), len(tgt_points))

    # Use astroalign to find matching stars and compute transformation
    transform, (src, dst) = aa.find_transform(
        tgt_points,
        ref_points,
        max_control_points=max_control_points,
    )

    return transform, src, dst