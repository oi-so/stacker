"""Image saving helpers for FITS, TIFF, PNG, and JPEG."""

from pathlib import Path
from typing import Any
import logging

from astropy.io import fits
from PIL import Image
import numpy as np
import tifffile

logger = logging.getLogger(__name__)


def _as_float32(array: np.ndarray) -> np.ndarray:
    return np.asarray(array, dtype=np.float32)


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _stretch_for_display(array: np.ndarray, bit_depth: int = 8) -> np.ndarray:
    image = _as_float32(array)
    finite = image[np.isfinite(image)]
    if finite.size == 0:
        image = np.zeros_like(image, dtype=np.float32)
    else:
        low, high = np.percentile(finite, (0.5, 99.5))
        if high <= low:
            low = float(np.min(finite))
            high = float(np.max(finite))
        image = np.clip((image - low) / (high - low + 1e-8), 0, 1)

    if bit_depth == 16:
        return (image * 65535).round().astype(np.uint16)
    return (image * 255).round().astype(np.uint8)


def _fits_header(metadata: dict[str, Any] | None = None, frame_type: str | None = None) -> fits.Header:
    header = fits.Header()
    if metadata:
        for key, value in metadata.items():
            fits_key = str(key).upper().replace(" ", "_")[:8]
            if fits_key in {"SIMPLE", "BITPIX", "NAXIS", "EXTEND"}:
                continue
            try:
                header[fits_key] = str(value)[:68]
            except Exception:
                continue
    if frame_type:
        header["FRAMTYP"] = frame_type
    header["CREATOR"] = "Astro Stacker"
    return header


def save_fits(
    array: np.ndarray,
    path: Path,
    *,
    metadata: dict[str, Any] | None = None,
    frame_type: str | None = None,
    bit_depth: int | None = None,
    **_: Any,
) -> None:
    """Save an image as FITS."""
    _ensure_parent(path)
    data = _as_float32(array)
    if data.ndim == 3 and data.shape[-1] <= 4:
        data = np.moveaxis(data, -1, 0)

    if bit_depth == 16:
        data_to_write = np.clip(data, 0, 65535).round().astype(np.uint16)
    else:
        data_to_write = data.astype(np.float32)

    fits.PrimaryHDU(data=data_to_write, header=_fits_header(metadata, frame_type)).writeto(
        path,
        overwrite=True,
    )
    logger.info("Saved FITS: %s", path)


def save_tiff(
    array: np.ndarray,
    path: Path,
    *,
    bit_depth: int | str = 16,
    **_: Any,
) -> None:
    """Save an image as TIFF, using 16-bit integer or 32-bit float pixels."""
    _ensure_parent(path)
    data = _as_float32(array)
    if bit_depth in {32, "float32"}:
        output = data.astype(np.float32)
    else:
        output = np.clip(data, 0, 65535).round().astype(np.uint16)
    tifffile.imwrite(path, output)
    logger.info("Saved TIFF: %s", path)


def save_png(
    array: np.ndarray,
    path: Path,
    *,
    bit_depth: int = 8,
    **_: Any,
) -> None:
    """Save an image as stretched PNG."""
    _ensure_parent(path)
    output = _stretch_for_display(array, 16 if bit_depth == 16 else 8)
    Image.fromarray(np.squeeze(output)).save(path)
    logger.info("Saved PNG: %s", path)


def save_jpeg(
    array: np.ndarray,
    path: Path,
    *,
    quality: int = 90,
    **_: Any,
) -> None:
    """Save an image as stretched 8-bit JPEG."""
    _ensure_parent(path)
    output = _stretch_for_display(array, 8)
    img = Image.fromarray(np.squeeze(output))
    if img.mode not in {"L", "RGB"}:
        img = img.convert("RGB")
    img.save(path, quality=max(0, min(100, int(quality))))
    logger.info("Saved JPEG: %s", path)


def save_image(array: np.ndarray, path: Path, **kwargs: Any) -> None:
    """Dispatch image saving by file suffix."""
    suffix = path.suffix.lower()
    if suffix in {".fits", ".fit", ".fts"}:
        save_fits(array, path, **kwargs)
    elif suffix in {".tif", ".tiff"}:
        save_tiff(array, path, **kwargs)
    elif suffix == ".png":
        save_png(array, path, **kwargs)
    elif suffix in {".jpg", ".jpeg"}:
        save_jpeg(array, path, **kwargs)
    else:
        raise ValueError(f"Unsupported output format: {path.suffix}")


def save_preview_tiff(image: np.ndarray, path: Path) -> None:
    """Compatibility helper: save a stretched 16-bit TIFF preview."""
    _ensure_parent(path)
    tifffile.imwrite(path, _stretch_for_display(image, 16))
