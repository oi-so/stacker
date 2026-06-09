from dataclasses import dataclass
from ..stacking.combiner import Method



@dataclass
class StackingSettings:
    method: Method = "mean"



@dataclass
class AlignmentSettings:
    max_stars: int = 500


@dataclass
class CalibrationSettings:
    use_darks: bool = False
    use_flats: bool = False
    use_flat_darks: bool = False
    use_biases: bool = False