"""Versioned JSON helpers; explicit type allowlist, no pickle or dynamic imports."""

import json
import math
import os
import tempfile
from dataclasses import fields, is_dataclass
from datetime import datetime
from enum import Enum
from functools import cache
from pathlib import Path

import numpy as np
from astropy.io import fits
from astropy.wcs import WCS


@cache
def _types():
    from ..io import image_data
    from ..moving_object import models
    from ..platesolve.solver import PlateSolveResult, PlateSolveSettings
    from ..stars.star_data import Star, StarCatalog
    from . import settings
    from .project import AlignmentSession, AlignmentSignature, ProjectSettings

    classes = [
        Star,
        StarCatalog,
        PlateSolveSettings,
        PlateSolveResult,
        AlignmentSession,
        AlignmentSignature,
        ProjectSettings,
    ]
    for module in (image_data, models, settings):
        classes.extend(
            value
            for value in vars(module).values()
            if isinstance(value, type) and (is_dataclass(value) or issubclass(value, Enum))
        )
    return {cls.__name__: cls for cls in classes}


def encode(value, base: Path):
    if isinstance(value, Enum):
        return {"$type": type(value).__name__, "value": value.value}
    if isinstance(value, Path):
        try:
            path = Path(os.path.relpath(value.resolve(), base.resolve())).as_posix()
        except ValueError:  # Different Windows drive.
            path = value.resolve().as_posix()
        return {"$path": path}
    if isinstance(value, datetime):
        return {"$date": value.isoformat()}
    if isinstance(value, WCS):
        return {"$wcs": value.to_header(relax=True).tostring()}
    if isinstance(value, np.ndarray):
        if value.size > 100:
            raise ValueError("Pixel arrays do not belong in project JSON")
        return {"$array": value.tolist()}
    if is_dataclass(value):
        return {
            "$type": type(value).__name__,
            "fields": {
                field.name: encode(getattr(value, field.name), base) for field in fields(value)
            },
        }
    if isinstance(value, dict):
        return {"$dict": [[encode(k, base), encode(v, base)] for k, v in value.items()]}
    if isinstance(value, (list, tuple, set, frozenset)):
        return {"$sequence": type(value).__name__, "items": [encode(v, base) for v in value]}
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def decode(value, base: Path):
    if not isinstance(value, dict):
        return value
    if "$path" in value:
        return (base / value["$path"]).resolve()
    if "$date" in value:
        return datetime.fromisoformat(value["$date"])
    if "$wcs" in value:
        return WCS(fits.Header.fromstring(value["$wcs"])).celestial
    if "$array" in value:
        array = np.asarray(value["$array"], dtype=np.float64)
        if array.shape != (3, 3) or not np.isfinite(array).all():
            raise ValueError("Invalid alignment matrix")
        if not np.allclose(array[2], [0, 0, 1]) or abs(np.linalg.det(array)) < 1e-12:
            raise ValueError("Invalid affine transform")
        return array
    if "$sequence" in value:
        cls = {"list": list, "tuple": tuple, "set": set, "frozenset": frozenset}[value["$sequence"]]
        return cls(decode(v, base) for v in value["items"])
    if "$dict" in value:
        return {decode(k, base): decode(v, base) for k, v in value["$dict"]}
    if "$type" in value:
        cls = _types()[value["$type"]]
        if issubclass(cls, Enum):
            return cls(value["value"])
        return cls(**{k: decode(v, base) for k, v in value["fields"].items()})
    raise ValueError("Unknown project value")


def fingerprint(path: Path):
    stat = path.stat()
    return (stat.st_size, stat.st_mtime_ns)


def atomic_write(path: Path, document):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(document, stream, ensure_ascii=False, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def read_document(path: Path, kind: str):
    if path.stat().st_size > 64 * 1024**2:
        raise ValueError("Project/history file exceeds 64 MiB")
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("format") != kind or document.get("version") != 1:
        raise ValueError("未対応のプロジェクト／履歴ファイル形式です。")
    return decode(document["data"], path.parent)


def write_document(path: Path, kind: str, data):
    atomic_write(path, {"format": kind, "version": 1, "data": encode(data, path.parent)})
