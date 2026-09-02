from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path


@dataclass(frozen=True, slots=True)
class SkyPosition:
    """ICRS/J2000 sky position in degrees."""

    ra_deg: float
    dec_deg: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.ra_deg) or not math.isfinite(self.dec_deg):
            raise ValueError("RA and Dec must be finite")
        if not -90.0 <= self.dec_deg <= 90.0:
            raise ValueError("Dec must be between -90 and 90 degrees")
        object.__setattr__(self, "ra_deg", self.ra_deg % 360.0)


@dataclass(frozen=True, slots=True)
class MovingObjectAnchor:
    """User-provided moving-object coordinate for one light frame."""

    frame_path: Path
    ra_deg: float
    dec_deg: float

    @property
    def position(self) -> SkyPosition:
        return SkyPosition(self.ra_deg, self.dec_deg)


class MovingObjectMode(StrEnum):
    MANUAL = "manual"
    CATALOG = "catalog"


@dataclass(frozen=True, slots=True)
class CatalogObject:
    """A selected JPL Small-Body Database object."""

    designation: str
    fullname: str
    spk_id: str | None = None
    kind: str | None = None


@dataclass(slots=True)
class MovingObjectSettings:
    enabled: bool = False
    mode: MovingObjectMode = MovingObjectMode.MANUAL
    anchors: list[MovingObjectAnchor] = field(default_factory=list)
    reference_frame_path: Path | None = None
    catalog_object: CatalogObject | None = None
    observer_code: str = "500"
