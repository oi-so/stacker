from dataclasses import dataclass

from ..io.image_data import (
    TransformData,
    AlignmentData
)


@dataclass
class AlignmentResult:
    transform: TransformData
    info: AlignmentData