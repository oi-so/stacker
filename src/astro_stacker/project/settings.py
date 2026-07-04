from dataclasses import dataclass
from enum import StrEnum



class StackingMethod(StrEnum):
    AVERAGE = "average"
    MEDIAN = "median"
    ADD = "add"
    SIGMA_CLIP = "sigma_clip"

    @property
    def show_name(self) -> str:
        return {
            StackingMethod.AVERAGE: "Average",
            StackingMethod.MEDIAN: "Median",
            StackingMethod.ADD: "Add",
            StackingMethod.SIGMA_CLIP: "Sigma Clipping",
        }[self]


@dataclass
class StackingSettings:
    method: StackingMethod = StackingMethod.AVERAGE
    sigma: float = 3.0
    iterations: int = 1


class AlignmentMode(StrEnum):
    ALL = "all"
    NEW_ONLY = "new_only"

class ReferenceMode(StrEnum):
    MIDDLE = "middle"
    BEST = "best"
    MANUAL = "manual"


@dataclass
class AlignmentSettings:
    max_stars: int = 500
    sigma: float = 5.0
    reference_mode: ReferenceMode = ReferenceMode.MIDDLE
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
