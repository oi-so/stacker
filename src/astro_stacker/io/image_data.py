"""Data structures for astronomical images and their metadata.

This module defines the core data classes used throughout astro_stacker:
- WCSData: World Coordinate System information
- TransformData: Alignment transformation parameters
- ScoreData: Image quality metrics
- ImageShape: Image dimensions
- AlignmentData: Star matching statistics
- AstroImageInfo: Image metadata
- AstroImage: Complete image container with lazy loading
"""

from dataclasses import dataclass, field, asdict
from pathlib import Path
import numpy as np
from enum import StrEnum

from ..utils.serializable import SerializableMixin


class ColorMode(StrEnum):
    MONO = "mono"
    RGB = "rgb"
    BAYER = "bayer"


class CFAType(StrEnum):
    NONE = "none"
    RGGB = "rggb"
    BGGR = "bggr"
    GBRG = "gbrg"
    GRBG = "grbg"


@dataclass
class WCSData(SerializableMixin):
    """World Coordinate System (WCS) information for an image.
    
    Attributes:
        ra: Right ascension in degrees (or None if unknown)
        dec: Declination in degrees (or None if unknown)
        pixel_scale: Arcsec per pixel (or None if unknown)
        rotation: Image rotation angle in degrees (or None if unknown)
    """
    ra: float | None = None
    dec: float | None = None
    pixel_scale: float | None = None
    rotation: float | None = None


@dataclass
class TransformData(SerializableMixin):
    """Image alignment transformation parameters.
    
    Stores both individual parameters and the full transformation matrix
    for aligning an image to a reference.
    
    Attributes:
        dx: X-axis translation in pixels
        dy: Y-axis translation in pixels
        rotation: Rotation angle in degrees
        scale: Scale factor relative to reference
        matrix: 3x3 homography/affine transformation matrix (optional)
    """
    dx: float = 0.0
    dy: float = 0.0
    rotation: float = 0.0
    scale: float = 1.0

    matrix: np.ndarray | None = None

    def to_dict(self) -> dict:
        data = asdict(self)

        if self.matrix is not None:
            data["matrix"] = self.matrix.tolist()

        return data

    @classmethod
    def from_dict(cls, data: dict):
        matrix = data.get("matrix")

        if matrix is not None:
            data["matrix"] = np.array(matrix)

        return cls(**data)


@dataclass
class ScoreData(SerializableMixin):
    """Image quality metrics and scoring information.
    
    Attributes:
        score: Overall quality score (star_count / (fwhm + 1e-6))
        star_count: Number of detected stars
        fwhm: Full Width at Half Maximum of stars in pixels
        ellipticity: Star ellipticity measure (if calculated)
        background_noise: Background noise standard deviation
        cloud_score: Cloud detection score (if calculated)
    """
    score: float | None = None

    star_count: int | None = None
    fwhm: float | None = None

    ellipticity: float | None = None

    background_noise: float | None = None

    cloud_score: float | None = None


    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "ScoreData":
        return cls(**data)


@dataclass
class ImageShape:
    """Image dimensions.
    
    Attributes:
        width: Image width in pixels
        height: Image height in pixels
        channels: Number of color channels (1 for grayscale, 3 for RGB, etc.)
    """
    width: int
    height: int
    channels: int



@dataclass
class AlignmentData(SerializableMixin):
    """Star matching statistics from image alignment.
    
    Attributes:
        reference_star_count: Number of stars in reference image
        matched_star_count: Number of matched stars between images
        rms_error: Root Mean Square error of alignment in pixels
    """
    reference_star_count: int | None = None
    matched_star_count: int | None = None
    rms_error: float | None = None



@dataclass
class AstroImageInfo(SerializableMixin):
    path: Path

    shape: ImageShape

    bit_depth: int

    color_mode: ColorMode
    cfa_type: CFAType = CFAType.NONE

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
    is_master: bool = False
    master_type: str | None = None


@dataclass
class AstroImage:
    """Complete container for an astronomical image with lazy loading.
    
    Uses lazy loading to minimize memory usage. Image data is loaded on demand
    and can be unloaded when not needed. This is managed by ImageManager.
    
    Attributes:
        info: Image metadata (AstroImageInfo)
        image: Image pixel data as numpy array, or None if not loaded
    """
    info: AstroImageInfo
    image: np.ndarray | None

    @property
    def is_loaded(self) -> bool:
        return self.image is not None

    def load(self) -> np.ndarray:
        from .loader import load_image

        if self.image is None:
            self.image = load_image(self)
        return self.image

    def unload(self) -> None:
        self.image = None
