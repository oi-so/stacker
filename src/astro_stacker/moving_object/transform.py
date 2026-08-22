from __future__ import annotations

import math
from typing import Protocol, cast

import numpy as np

from ..io.image_data import AstroImage, TransformData
from .capture_time import frame_parameters
from .models import MovingObjectAnchor
from .trajectory import SphericalTrajectory, TrajectoryAnchor


class CelestialWCS(Protocol):
    has_celestial: bool

    def world_to_pixel_values(self, ra_deg: float, dec_deg: float) -> tuple[object, object]: ...


def compose_moving_object_transform(
    star_transform: TransformData,
    dx: float,
    dy: float,
) -> TransformData:
    """Add an aligned-image translation to a source-to-reference transform."""

    if star_transform.matrix is None:
        raise ValueError("The frame has no star-alignment matrix")

    translation = np.array(
        [[1.0, 0.0, dx], [0.0, 1.0, dy], [0.0, 0.0, 1.0]],
        dtype=np.float64,
    )
    matrix = translation @ np.asarray(star_transform.matrix, dtype=np.float64)
    scale = math.hypot(float(matrix[0, 0]), float(matrix[1, 0]))
    rotation = math.degrees(math.atan2(float(matrix[1, 0]), float(matrix[0, 0])))
    return TransformData(
        dx=float(matrix[0, 2]),
        dy=float(matrix[1, 2]),
        rotation=rotation,
        scale=scale,
        matrix=matrix,
    )


class MovingObjectTransformBuilder:
    """Build one-pass source-to-moving-object-reference transforms."""

    def __init__(
        self,
        frames: list[AstroImage],
        alignment_reference_frame: AstroImage,
        anchors: list[MovingObjectAnchor],
        target_reference_frame: AstroImage | None = None,
    ) -> None:
        if not frames:
            raise ValueError("No enabled light frames")

        frame_by_path = {frame.info.path: frame for frame in frames}
        if alignment_reference_frame.info.path not in frame_by_path:
            raise ValueError("The alignment reference frame is not enabled")
        if target_reference_frame is None:
            target_reference_frame = alignment_reference_frame
        if target_reference_frame.info.path not in frame_by_path:
            raise ValueError("The moving-object reference frame is not enabled")

        parameters, self.uses_capture_time = frame_parameters(frames)
        trajectory_anchors: list[TrajectoryAnchor] = []
        for anchor in anchors:
            if anchor.frame_path not in frame_by_path:
                raise ValueError(f"Moving-object anchor is not enabled: {anchor.frame_path.name}")
            trajectory_anchors.append(
                TrajectoryAnchor(parameters[anchor.frame_path], anchor.position)
            )

        self.parameters = parameters
        self.trajectory = SphericalTrajectory(trajectory_anchors)
        self.alignment_reference_frame = alignment_reference_frame
        self.target_reference_frame = target_reference_frame
        raw_wcs = alignment_reference_frame.info.wcs

        if raw_wcs is None or not callable(getattr(raw_wcs, "world_to_pixel_values", None)):
            raise ValueError("参照画像にWCSがありません。先にPlate Solveを実行してください。")
        if hasattr(raw_wcs, "has_celestial") and not raw_wcs.has_celestial:
            raise ValueError("参照画像のWCSに天球座標がありません。")
        self.wcs = cast(CelestialWCS, raw_wcs)

        reference_position = self.trajectory.position_at(parameters[target_reference_frame.info.path])
        self.reference_pixel = self._world_to_pixel(reference_position.ra_deg, reference_position.dec_deg)

        # Validate coverage before expensive image processing starts.
        for parameter in parameters.values():
            self.trajectory.position_at(parameter)

    def _world_to_pixel(self, ra_deg: float, dec_deg: float) -> tuple[float, float]:
        x, y = self.wcs.world_to_pixel_values(ra_deg, dec_deg)
        x_value = float(np.asarray(x))
        y_value = float(np.asarray(y))
        if not math.isfinite(x_value) or not math.isfinite(y_value):
            raise ValueError("WCS returned a non-finite moving-object position")
        return x_value, y_value

    def transform_for(self, frame: AstroImage) -> TransformData:
        try:
            parameter = self.parameters[frame.info.path]
        except KeyError as exc:
            raise ValueError(f"Frame is not part of the moving-object alignment: {frame.info.path}") from exc

        position = self.trajectory.position_at(parameter)
        x, y = self._world_to_pixel(position.ra_deg, position.dec_deg)
        reference_x, reference_y = self.reference_pixel
        return compose_moving_object_transform(
            frame.info.transform,
            reference_x - x,
            reference_y - y,
        )
