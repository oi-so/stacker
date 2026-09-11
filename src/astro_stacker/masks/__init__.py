"""Reusable float32 mask and weight primitives."""

from .artifacts import (
    detect_line_candidates,
    inpaint_masked_pixels,
    polygon_weight_mask,
    polyline_weight_mask,
)
from .stars import generate_star_mask
from .weights import (
    AlignedMaskProvider,
    AlignmentValidityMaskProvider,
    ArrayMaskProvider,
    CompositeMaskProvider,
    ConstantMaskProvider,
    FileMaskProvider,
    WeightMaskProvider,
    compose_masks,
    validity_mask,
)

__all__ = [
    "AlignedMaskProvider",
    "AlignmentValidityMaskProvider",
    "ArrayMaskProvider",
    "CompositeMaskProvider",
    "ConstantMaskProvider",
    "FileMaskProvider",
    "WeightMaskProvider",
    "compose_masks",
    "detect_line_candidates",
    "generate_star_mask",
    "inpaint_masked_pixels",
    "polygon_weight_mask",
    "polyline_weight_mask",
    "validity_mask",
]
