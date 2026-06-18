"""Standard image format loader (PNG, JPEG, TIFF).

Loads standard image formats using PIL/Pillow.
"""

from PIL import Image
import numpy as np
from pathlib import Path
import exifread

from .image_data import AstroImageInfo, AstroImage, ImageShape, ColorMode, CFAType


def load_standard_info(path: Path) -> AstroImage:
    """Load standard image metadata.
    
    Args:
        path: Path to image file (PNG, JPEG, TIFF, etc.)
        
    Returns:
        AstroImage with metadata
    """
    with Image.open(path) as img:
        width, height = img.size
        mode = img.mode
        bit_depth = 16 if mode in {"I;16", "I;16B", "I;16L"} else 8
        if mode in {"I", "F"}:
            bit_depth = 32

        bands = len(img.getbands())
        if bands == 1:
            color_mode = ColorMode.MONO
        else:
            color_mode = ColorMode.RGB

        with open(path, 'rb') as f:
            exif_data = exifread.process_file(f)
        return AstroImage(
            info=AstroImageInfo(
                path=path,
                shape=ImageShape(width=width, height=height, channels=len(img.getbands()) if img.getbands() else 1),
                bit_depth=bit_depth,
                color_mode=color_mode,
                cfa_type=CFAType.NONE,
                f_number=exif_data.get('EXIF FNumber').values[0].num / exif_data.get('EXIF FNumber').values[0].den if 'EXIF FNumber' in exif_data else None,
                exposure_time=exif_data.get('EXIF ExposureTime').values[0].num / exif_data.get('EXIF ExposureTime').values[0].den if 'EXIF ExposureTime' in exif_data else None,
                iso=exif_data.get('EXIF ISOSpeedRatings').values[0] if 'EXIF ISOSpeedRatings' in exif_data else None,
                exif={tag: str(value) for tag, value in exif_data.items()}
            ),
            image=None
        )
    

def load_standard_image(path: Path) -> np.ndarray:
    """Load standard image pixel data.
    
    Args:
        path: Path to image file
        
    Returns:
        Pixel data as RGB numpy array (uint8)
    """
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
        return np.clip(data, 0, None)
