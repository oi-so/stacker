from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .models import SkyPosition


@dataclass(frozen=True, slots=True)
class TrajectoryAnchor:
    parameter: float
    position: SkyPosition


def _to_unit_vector(position: SkyPosition) -> np.ndarray:
    ra = math.radians(position.ra_deg)
    dec = math.radians(position.dec_deg)
    cos_dec = math.cos(dec)
    return np.array(
        [cos_dec * math.cos(ra), cos_dec * math.sin(ra), math.sin(dec)],
        dtype=np.float64,
    )


def _from_unit_vector(vector: np.ndarray) -> SkyPosition:
    vector = vector / np.linalg.norm(vector)
    ra = math.degrees(math.atan2(float(vector[1]), float(vector[0]))) % 360.0
    dec = math.degrees(math.asin(float(np.clip(vector[2], -1.0, 1.0))))
    return SkyPosition(ra, dec)


def _slerp(start: SkyPosition, end: SkyPosition, fraction: float) -> SkyPosition:
    a = _to_unit_vector(start)
    b = _to_unit_vector(end)
    dot = float(np.clip(np.dot(a, b), -1.0, 1.0))

    if dot > 0.999999:
        vector = (1.0 - fraction) * a + fraction * b
        return _from_unit_vector(vector)

    if dot < -0.999999:
        raise ValueError("Cannot interpolate between antipodal sky positions")

    angle = math.acos(dot)
    sin_angle = math.sin(angle)
    vector = (
        math.sin((1.0 - fraction) * angle) / sin_angle * a
        + math.sin(fraction * angle) / sin_angle * b
    )
    return _from_unit_vector(vector)


class SphericalTrajectory:
    """Piecewise great-circle interpolation between user anchors."""

    def __init__(self, anchors: list[TrajectoryAnchor]) -> None:
        if len(anchors) < 2:
            raise ValueError("At least two moving-object anchors are required")

        self.anchors = sorted(anchors, key=lambda anchor: anchor.parameter)
        parameters = [anchor.parameter for anchor in self.anchors]
        if len(parameters) != len(set(parameters)):
            raise ValueError("Moving-object anchors must have different times or frame positions")

    @property
    def start_parameter(self) -> float:
        return self.anchors[0].parameter

    @property
    def end_parameter(self) -> float:
        return self.anchors[-1].parameter

    def position_at(self, parameter: float) -> SkyPosition:
        tolerance = 1e-9
        if parameter < self.start_parameter - tolerance or parameter > self.end_parameter + tolerance:
            raise ValueError("Moving-object anchors do not cover all enabled light frames")

        if parameter <= self.start_parameter:
            return self.anchors[0].position
        if parameter >= self.end_parameter:
            return self.anchors[-1].position

        for start, end in zip(self.anchors, self.anchors[1:]):
            if start.parameter <= parameter <= end.parameter:
                fraction = (parameter - start.parameter) / (end.parameter - start.parameter)
                return _slerp(start.position, end.position, fraction)

        raise RuntimeError("Failed to find a trajectory segment")
