"""Star matching and transformation calculation.

Matches stars between two catalogs and computes the transformation
using the astroalign library.
"""

import numpy as np
import astroalign as aa

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
    ref_points = np.array([
        [s.x, s.y]
        for s in reference.stars
    ])

    tgt_points = np.array([
        [s.x, s.y]
        for s in target.stars
    ])

    # Use astroalign to find matching stars and compute transformation
    transform, (src, dst) = aa.find_transform(
        tgt_points,
        ref_points
    )

    return transform, src, dst