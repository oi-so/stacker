from __future__ import annotations

import math

import numpy as np

from ..io.image_data import AstroImage
from ..project.project import Project
from .capture_time import frame_parameters
from .trajectory import SphericalTrajectory, TrajectoryAnchor


def moving_object_preview_pixel(
    project: Project,
    frame: AstroImage,
    *,
    aligned: bool,
    scale_x: float = 1.0,
    scale_y: float = 1.0,
) -> tuple[float, float] | None:
    """Predict the configured object's pixel in an aligned or raw preview."""

    frames = [item for item in project.light_frames if item.info.enabled]
    settings = project.settings.moving_object
    reference = project.reference_image
    if len(settings.anchors) < 2 or reference is None or frame not in frames:
        return None
    wcs = reference.info.wcs
    if wcs is None or not callable(getattr(wcs, "world_to_pixel_values", None)):
        return None

    try:
        parameters, _ = frame_parameters(frames)
        trajectory = SphericalTrajectory(
            [
                TrajectoryAnchor(parameters[anchor.frame_path], anchor.position)
                for anchor in settings.anchors
                if anchor.frame_path in parameters
            ]
        )
        position = trajectory.position_at(parameters[frame.info.path])
        x_raw, y_raw = wcs.world_to_pixel_values(position.ra_deg, position.dec_deg)
        point = np.array([float(np.asarray(x_raw)), float(np.asarray(y_raw)), 1.0])

        if not aligned and frame is not reference:
            matrix = frame.info.transform.matrix
            if matrix is None:
                return None
            point = np.linalg.inv(np.asarray(matrix, dtype=np.float64)) @ point
            if abs(point[2]) < 1e-12:
                return None
            point /= point[2]
        x = float(point[0]) * scale_x
        y = float(point[1]) * scale_y
        if not math.isfinite(x) or not math.isfinite(y):
            return None
        return x, y
    except (KeyError, ValueError, np.linalg.LinAlgError):
        return None
