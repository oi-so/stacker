from dataclasses import dataclass, field
from pathlib import Path
import numpy as np


@dataclass
class WCSData:
    ra: float | None = None
    dec: float | None = None
    pixel_scale: float | None = None
    rotation: float | None = None


@dataclass
class TransformData:
    dx: float = 0.0
    dy: float = 0.0
    rotation: float = 0.0
    scale: float = 1.0


@dataclass
class ScoreData:
    score: float | None = None

    star_count: int | None = None
    fwhm: float | None = None

    ellipticity: float | None = None

    background_noise: float | None = None

    cloud_score: float | None = None


@dataclass
class ImageShape:
    width: int
    height: int
    channels: int



@dataclass
class AlignmentData:
    reference_star_count: int | None = None
    matched_star_count: int | None = None
    rms_error: float | None = None



@dataclass
class AstroImageInfo:
    path: Path

    shape: ImageShape

    bit_depth: int

    exposure_time: float | None = None
    iso: int | None = None
    f_number: float | None = None

    exif: dict | None = None

    wcs: WCSData = field(
        default_factory=WCSData
    )

    score_data: ScoreData = field(
        default_factory=ScoreData
    )

    transform: TransformData = field(
        default_factory=TransformData
    )

    alignment_data: AlignmentData = field(
        default_factory=AlignmentData
    )

    enabled: bool = True


@dataclass
class AstroImage:
    info: AstroImageInfo
    image: np.ndarray | None

    @property
    def is_loaded(self) -> bool:
        return self.image is not None
    
    def load(self) -> None:
        from .loader import load_image

        if self.image is None:
            self.image = load_image(self)

    def unload(self) -> None:
        del self.image
        self.image = None