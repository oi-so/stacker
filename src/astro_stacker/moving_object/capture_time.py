from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from ..io.image_data import AstroImage

_EXIF_FORMATS = (
    "%Y:%m:%d %H:%M:%S.%f",
    "%Y:%m:%d %H:%M:%S",
    "%Y-%m-%d %H:%M:%S.%f",
    "%Y-%m-%d %H:%M:%S",
)


def _parse_capture_time(value: object) -> datetime | None:
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        parsed = None

    if parsed is None:
        for date_format in _EXIF_FORMATS:
            try:
                parsed = datetime.strptime(text, date_format).replace(tzinfo=UTC)
                break
            except ValueError:
                continue

    if parsed is None:
        return None

    # DATE-OBS is normally UTC. Most camera EXIF timestamps have no timezone,
    # but relative intervals remain correct when all frames use the same clock.
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def capture_midpoint(frame: AstroImage) -> datetime | None:
    """Return the exposure midpoint, or None when no capture time is available."""

    metadata = frame.info.exif or {}
    value = frame.info.capture_time_override_utc or (
        metadata.get("DATE-OBS")
        or metadata.get("EXIF DateTimeOriginal")
        or metadata.get("Image DateTime")
    )
    start = _parse_capture_time(value)
    if start is None:
        return None

    exposure = frame.info.exposure_time or 0.0
    return start + timedelta(seconds=max(0.0, float(exposure)) / 2.0)


def corrected_capture_starts(
    frames: list[AstroImage],
    first_start: datetime,
    fallback_interval_seconds: float,
) -> dict[Path, datetime]:
    """Re-base a sequence from one corrected first-frame timestamp.

    When every original timestamp is available, its actual interval from the
    first frame is preserved.  Otherwise list order and the supplied cadence
    are used consistently for the whole sequence.
    """

    if first_start.tzinfo is None:
        first_start = first_start.replace(tzinfo=UTC)
    first_start = first_start.astimezone(UTC)
    if fallback_interval_seconds <= 0:
        raise ValueError("Frame interval must be greater than zero")

    originals: list[datetime | None] = []
    for frame in frames:
        override = frame.info.capture_time_override_utc
        frame.info.capture_time_override_utc = None
        try:
            midpoint = capture_midpoint(frame)
        finally:
            frame.info.capture_time_override_utc = override
        if midpoint is not None:
            midpoint -= timedelta(seconds=max(0.0, float(frame.info.exposure_time or 0.0)) / 2.0)
        originals.append(midpoint)

    if frames and all(value is not None for value in originals):
        origin = originals[0]
        assert origin is not None
        return {
            frame.info.path: first_start + (value - origin)
            for frame, value in zip(frames, originals, strict=True)
            if value is not None
        }
    cadence = timedelta(seconds=float(fallback_interval_seconds))
    return {
        frame.info.path: first_start + index * cadence
        for index, frame in enumerate(frames)
    }


def apply_corrected_capture_starts(
    frames: list[AstroImage], corrected: dict[Path, datetime]
) -> None:
    for frame in frames:
        value = corrected.get(frame.info.path)
        frame.info.capture_time_override_utc = (
            value.astimezone(UTC).isoformat().replace("+00:00", "Z") if value else None
        )


def frame_parameters(frames: list[AstroImage]) -> tuple[dict[Path, float], bool]:
    """Map frame paths to time parameters.

    Capture time is preferred. If any frame lacks it, list order is used for
    every frame so the parameter system remains internally consistent.
    """

    midpoints = [capture_midpoint(frame) for frame in frames]
    if frames and all(value is not None for value in midpoints):
        first = min(value for value in midpoints if value is not None)
        return (
            {
                frame.info.path: (value - first).total_seconds()
                for frame, value in zip(frames, midpoints, strict=True)
                if value is not None
            },
            True,
        )

    return ({frame.info.path: float(index) for index, frame in enumerate(frames)}, False)
