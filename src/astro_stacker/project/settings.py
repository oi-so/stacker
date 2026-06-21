from dataclasses import dataclass
from ..stacking.combiner import Method
from enum import StrEnum



@dataclass
class StackingSettings:
    method: Method = "mean"
    sigma: float = 3.0
    iterations: int = 1


class AlignmentMode(StrEnum):
    ALL = "all"
    NEW_ONLY = "new_only"


@dataclass
class AlignmentSettings:
    max_stars: int = 500
    sigma: float = 5.0
    reference_mode: str = "middle"
    calibrate_before_align: bool = True
    mode: AlignmentMode = AlignmentMode.ALL


@dataclass
class CalibrationSettings:
    use_darks: bool = False
    use_flats: bool = False
    use_flat_darks: bool = False
    use_biases: bool = False



class DebayerTiming(StrEnum):
    BEFORE_STACK = "before_stack"
    AFTER_STACK = "after_stack"
