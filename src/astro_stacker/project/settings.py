from dataclasses import dataclass
from ..stacking.combiner import Method



@dataclass
class StackingSettings:
    method: Method = "mean"



@dataclass
class AlignmentSettings:
    max_stars: int = 500