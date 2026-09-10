from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path


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


@dataclass
class DrizzleSettings:
    enabled: bool = False
    scale: int = 2
    pixfrac: float = 0.8


@dataclass
class CosmeticCorrectionSettings:
    enabled: bool = False
    bad_pixel_map_path: Path | None = None
    method: str = "median"


@dataclass
class ArtifactMaskSettings:
    enabled: bool = False
    mask_paths: dict[Path, Path] = field(default_factory=dict)
    line_width: float = 8.0
    feather: float = 3.0


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
    local_scale: float = 32.0
    detail_strength: float = 1.0


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


class NightscapeOutput(StrEnum):
    SKY_ONLY = "sky_only"
    GROUND_ONLY = "ground_only"
    MASK_ONLY = "mask_only"
    MATERIALS = "materials"
    FINAL = "final"


class BoundaryMode(StrEnum):
    GROUND_MASK = "ground_mask"
    LIGHT_POLLUTION = "light_pollution"
    USER_MASK = "user_mask"


class GroundSource(StrEnum):
    SAME_FRAMES = "same_frames"
    SEPARATE_FRAMES = "separate_frames"


@dataclass
class NightscapeSettings:
    output: NightscapeOutput = NightscapeOutput.FINAL
    boundary_mode: BoundaryMode = BoundaryMode.GROUND_MASK
    ground_source: GroundSource = GroundSource.SAME_FRAMES
    star_alignment: bool = True
    ground_alignment: bool = False
    use_star_mask: bool = True
    split_mode: str = "none"
    split_index: int = 0
    feather: float = 4.0
    blur_scale: float = 32.0
    transition_width: float = 16.0
    background_strength: float = 0.25


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
    nightscape: NightscapeSettings = field(default_factory=NightscapeSettings)
    drizzle: DrizzleSettings = field(default_factory=DrizzleSettings)
    cosmetic_correction: CosmeticCorrectionSettings = field(
        default_factory=CosmeticCorrectionSettings
    )
    artifact_masks: ArtifactMaskSettings = field(default_factory=ArtifactMaskSettings)
    parallel_workers: int = 0


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
    use_wcs: bool = False
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
