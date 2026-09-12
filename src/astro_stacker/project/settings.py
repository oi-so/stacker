from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from ..core.resources import (
    DISK_RESERVE_BYTES,
    IMAGE_CACHE_BYTES,
    STACK_DISK_BYTES,
    STACK_MEMORY_BYTES,
)


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
    sigma: float = 2.0
    iterations: int = 5
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
    source: str = "map"
    bad_pixel_map_path: Path | None = None
    method: str = "median"
    light_sigma: float = 10.0
    light_persistence: float = 0.7


class ObstacleMode(StrEnum):
    NONE = "none"
    FIXED = "fixed"
    TRACKED = "tracked"


@dataclass
class ArtifactMaskSettings:
    enabled: bool = False
    mode: ObstacleMode = ObstacleMode.FIXED
    mask_paths: dict[Path, Path] = field(default_factory=dict)
    reference_mask_path: Path | None = None
    reference_frame_path: Path | None = None
    auto_detect_new: bool = False
    confidence_threshold: float = 0.6
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
    window_size: int = 5
    step: int = 1
    include_partial: bool = False
    alignment: AlignmentStrategy = AlignmentStrategy.STAR_GLOBAL


@dataclass
class ResourceSettings:
    temp_directory: Path | None = None
    image_cache_bytes: int = IMAGE_CACHE_BYTES
    stack_memory_bytes: int = STACK_MEMORY_BYTES
    stack_disk_bytes: int = STACK_DISK_BYTES
    disk_reserve_bytes: int = DISK_RESERVE_BYTES


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


class NightscapeCaptureMode(StrEnum):
    """How the sky and ground source material was captured."""

    FIXED = "fixed"
    TRACKING = "tracking"


@dataclass
class NightscapeSettings:
    output: NightscapeOutput = NightscapeOutput.FINAL
    boundary_mode: BoundaryMode = BoundaryMode.GROUND_MASK
    ground_source: GroundSource = GroundSource.SAME_FRAMES
    capture_mode: NightscapeCaptureMode = NightscapeCaptureMode.FIXED
    # These paths deliberately live in the project manifest.  A mask or a
    # separately photographed ground sequence should be reusable next time,
    # rather than being a one-run dialog choice.
    ground_frame_paths: list[Path] = field(default_factory=list)
    ground_mask_path: Path | None = None
    ground_use_single_frame: bool = False
    ground_stack: StackingSettings = field(default_factory=StackingSettings)
    # Empty means the legacy ``output`` choice controls exports.  New projects
    # select exactly the products they need through the nightscape dialog.
    enabled_outputs: set[str] = field(default_factory=set)
    star_alignment: bool = True
    ground_alignment: bool = False
    use_star_mask: bool = True
    split_mode: str = "none"
    split_index: int = 0
    feather: float = 4.0
    blur_scale: float = 32.0
    transition_width: float = 16.0
    background_strength: float = 0.25
    smooth_boundary: bool = True
    boundary_smoothing: str = "gaussian"


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
    resources: ResourceSettings = field(default_factory=ResourceSettings)


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
    star_fwhm: float = 4.0
    reference_mode: ReferenceMode = ReferenceMode.MIDDLE
    calibrate_before_align: bool = True
    use_wcs: bool = False
    mode: AlignmentMode = AlignmentMode.ALL
    alignment_sharpness_min: float = 0.20
    alignment_roundness_max: float = 0.50


@dataclass
class CalibrationSettings:
    use_darks: bool = False
    use_flats: bool = False
    use_flat_darks: bool = False
    use_biases: bool = False



class DebayerTiming(StrEnum):
    BEFORE_STACK = "before_stack"
    AFTER_STACK = "after_stack"
