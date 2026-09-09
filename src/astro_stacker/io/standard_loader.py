"""Standard image format loader (PNG, JPEG, TIFF).

Loads standard image formats using PIL/Pillow.
"""

from PIL import Image
import numpy as np
from pathlib import Path
import exifread
import tifffile

from .image_data import AstroImageInfo, AstroImage, ImageShape, ColorMode, CFAType


def load_standard_info(path: Path) -> AstroImage:
    """Load standard image metadata.
    
    Args:
        path: Path to image file (PNG, JPEG, TIFF, etc.)
        
    Returns:
        AstroImage with metadata
    """
    if path.suffix.lower() in {".tif", ".tiff"}:
        with tifffile.TiffFile(path) as tif:
            page = tif.pages[0]
            width, height = page.imagewidth, page.imagelength
            channels = page.samplesperpixel
            depth = page.dtype.itemsize * 8
        with path.open("rb") as stream:
            exif_data = exifread.process_file(stream, details=False)
        def number(tag):
            entry = exif_data.get(tag)
            if entry is None:
                return None
            value = entry.values[0]
            return float(value.num / value.den) if hasattr(value, "num") else float(value)
        return AstroImage(AstroImageInfo(
            path=path, shape=ImageShape(width, height, channels), bit_depth=depth,
            color_mode=ColorMode.MONO if channels == 1 else ColorMode.RGB,
            exposure_time=number("EXIF ExposureTime"), f_number=number("EXIF FNumber"),
            iso=number("EXIF ISOSpeed") or number("EXIF ISOSpeedRatings"),
            exif={tag: str(value) for tag, value in exif_data.items()},
        ))
    with Image.open(path) as img:
        width, height = img.size
        mode = img.mode
        exif_ifd = img.getexif().get_ifd(34665)
        bit_depth = 16 if mode in {"I;16", "I;16B", "I;16L"} else 8
        if mode in {"I", "F"}:
            bit_depth = 32

        bands = len(img.getbands())
        if bands == 1:
            color_mode = ColorMode.MONO
        else:
            color_mode = ColorMode.RGB

        with open(path, 'rb') as f:
            exif_data = exifread.process_file(f, details=False)
        return AstroImage(
            info=AstroImageInfo(
                path=path,
                shape=ImageShape(width=width, height=height, channels=len(img.getbands()) if img.getbands() else 1),
                bit_depth=bit_depth,
                color_mode=color_mode,
                cfa_type=CFAType.NONE,
                f_number=exif_data.get('EXIF FNumber').values[0].num / exif_data.get('EXIF FNumber').values[0].den if 'EXIF FNumber' in exif_data else (float(exif_ifd[33437]) if 33437 in exif_ifd else None),
                exposure_time=exif_data.get('EXIF ExposureTime').values[0].num / exif_data.get('EXIF ExposureTime').values[0].den if 'EXIF ExposureTime' in exif_data else (float(exif_ifd[33434]) if 33434 in exif_ifd else None),
                iso=exif_data.get('EXIF ISOSpeedRatings').values[0] if 'EXIF ISOSpeedRatings' in exif_data else (exif_ifd.get(34867) or exif_ifd.get(34855)),
                exif={tag: str(value) for tag, value in exif_data.items()}
            )
        )
    

def load_standard_image(path: Path) -> np.ndarray:
    """Load standard image pixel data.
    
    Args:
        path: Path to image file
        
    Returns:
        Pixel data as RGB numpy array (uint8)
    """
    if path.suffix.lower() in {".tif", ".tiff"}:
        with tifffile.TiffFile(path) as tif:
            page = tif.pages[0]
            data = page.asarray()
            if data.ndim == 3 and page.planarconfig == 2:
                data = np.moveaxis(data, 0, -1)
        if data.ndim == 2:
            data = data[..., np.newaxis]
        if data.ndim != 3:
            raise ValueError(f"Unsupported TIFF shape: {data.shape}")
        original_dtype = data.dtype
        data = data.astype(np.float32)
        if original_dtype == np.uint8:
            data *= 257.0
        return np.clip(data, 0, None, out=data)
    with Image.open(path) as img:
        # Ensure image is in RGB format for consistent handling
        data = np.array(img)
        original_dtype = data.dtype
        if data.ndim == 2:
            data = data[..., np.newaxis]
        data = data.astype(np.float32)
        if original_dtype == np.uint8:
            # Use a 16-bit working range for 8-bit standard images so preview
            # and calibration math operate on the same nominal range.
            data *= 257.0
        return np.clip(data, 0, None, out=data)
