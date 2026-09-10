from dataclasses import dataclass, field
from enum import StrEnum


class StackingMethod(StrEnum):
    AVERAGE = "average"
    MEDIAN = "median"
    ADD = "add"
    SIGMA_CLIP = "sigma_clip"
    MAXIMUM = "maximum"
    MINIMUM = "minimum"
    MINMAX_MEAN = "minmax_mean"

    @property
    def show_name(self) -> str:
        return {
            StackingMethod.AVERAGE: "Average",
            StackingMethod.MEDIAN: "Median",
            StackingMethod.ADD: "Add",
            StackingMethod.SIGMA_CLIP: "Sigma Clipping",
            StackingMethod.MAXIMUM: "比較明 (Maximum)",
            StackingMethod.MINIMUM: "比較暗 (Minimum)",
            StackingMethod.MINMAX_MEAN: "最大・最小除外平均",
        }[self]


@dataclass
class StackingSettings:
    method: StackingMethod = StackingMethod.AVERAGE
    sigma: float = 3.0
    iterations: int = 1
    use_weight_masks: bool = False
    use_quality_weights: bool = False
    exposure_normalization: bool = False
    background_normalization: str = "none"


class InvalidPixelPolicy(StrEnum):
    ZERO = "zero"
    NAN = "nan"
    KEEP_MASK = "keep_mask"


class FrameSelectionMode(StrEnum):
    ALL = "all"
    TOP_PERCENT = "top_percent"
    TOP_COUNT = "top_count"
    SCORE_THRESHOLD = "score_threshold"
    MANUAL = "manual"


@dataclass
class FrameSelectionSettings:
    mode: FrameSelectionMode = FrameSelectionMode.ALL
    value: float = 100.0


@dataclass
class StarMaskSettings:
    minimum_flux: float = 0.0
    radius_scale: float = 1.5
    expansion: float = 0.0
    feather: float = 1.0
    bright_star_scale: float = 0.25
    include_halos: bool = True
    elliptical: bool = True
    inverted: bool = False


class HDRStopAfter(StrEnum):
    EXPOSURE_STACKS = "exposure_stacks"
    MERGE = "merge"
    TONE_MAP = "tone_map"


@dataclass
class HDRSettings:
    auto_group: bool = True
    manual_groups: dict[str, str] = field(default_factory=dict)
    group_tolerance: float = 0.01
    stop_after: HDRStopAfter = HDRStopAfter.MERGE
    saturation_mode: str = "auto"
    black_level: float | None = None
    white_level: float | None = None
    tone_mapping: str = "global"


class AlignmentStrategy(StrEnum):
    STAR_PER_GROUP = "star_per_group"
    STAR_GLOBAL = "star_global"
    NONE = "none"
    GROUND = "ground"
    AUTO = "auto"


@dataclass
class TimelapseSettings:
    window_size: int = 10
    step: int = 10
    include_partial: bool = True
    alignment: AlignmentStrategy = AlignmentStrategy.NONE


@dataclass
class ExportSettings:
    suffix: str = ".fits"
    bit_depth: int | str | None = None
    invalid_pixels: InvalidPixelPolicy = InvalidPixelPolicy.ZERO
    save_validity_mask: bool = False
    continue_to_stack: bool = False


@dataclass
class ProcessingOptions:
    frame_selection: FrameSelectionSettings = field(default_factory=FrameSelectionSettings)
    star_mask: StarMaskSettings = field(default_factory=StarMaskSettings)
    hdr: HDRSettings = field(default_factory=HDRSettings)
    timelapse: TimelapseSettings = field(default_factory=TimelapseSettings)


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
