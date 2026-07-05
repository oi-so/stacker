from dataclasses import dataclass
from astropy.wcs import WCS
from pathlib import Path


@dataclass(slots=True)
class PlateSolveResult:
    success: bool

    message: str = ""

    center_ra: float | None = None
    center_dec: float | None = None

    pixel_scale: float | None = None
    rotation: float | None = None

    width: int | None = None
    height: int | None = None

    wcs: WCS | None = None
    solved_file: Path | None = None