"""Metadata snapshot of the frames actually consumed by a completed stack."""

import math
from collections import Counter


def _positive(value):
    try:
        number = float(value)
        return number if math.isfinite(number) and number > 0 else None
    except (TypeError, ValueError):
        return None


def stack_metadata(frames, method):
    result = {"NSTACK": len(frames), "STACKMTH": str(method)}
    summaries = []
    for attr, label, tag in [
        ("exposure_time", "Exposure(s)", "EXPTIME"),
        ("iso", "ISO", "ISO"),
        ("f_number", "FNumber", "FNUMBER"),
    ]:
        values = [_positive(getattr(frame.info, attr)) for frame in frames]
        counts = Counter(v for v in values if v is not None)
        missing = values.count(None)
        if counts:
            if attr == "exposure_time":
                result[tag] = math.fsum(v for v in values if v is not None)
            else:
                result[tag] = counts.most_common(1)[0][0]  # Ties: first source frame.
                if attr == "iso":
                    result[tag] = round(result[tag])
        summary = ", ".join(f"{value:g} x {count}" for value, count in counts.items())
        if missing:
            summary += f"; unknown x {missing}"
        summaries.append(f"{label}: {summary}")
    result["COMMENT"] = (
        f"Astro Stacker; {len(frames)} frames; method={method}. "
        + "; ".join(summaries)
        + ". ExposureTime is the sum of known exposures; ISO/FNumber are modes "
        "(ties use first input)."
    )
    return result
