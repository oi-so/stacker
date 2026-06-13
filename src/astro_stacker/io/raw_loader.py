"""RAW image format loader.

Loads RAW files from digital cameras using rawpy.
"""

import rawpy
import numpy as np
from pathlib import Path
import exifread
from .image_data import AstroImageInfo, AstroImage, ImageShape
from .image_data import ColorMode, CFAType


def load_raw_info(path: Path) -> AstroImage:
    """Load RAW image metadata.
    
    Args:
        path: Path to RAW file
        
    Returns:
        AstroImage with metadata from RAW header and EXIF
    """
    with rawpy.imread(str(path)) as raw:
        height, width = raw.sizes.height, raw.sizes.width
        channels = raw.raw_colors

        pattern = raw.raw_pattern
        cfa_type = CFAType.NONE

        if pattern is not None:
            mapping = {
                (0, 1, 1, 2): CFAType.RGGB,
                (2, 1, 1, 0): CFAType.BGGR,
                (1, 0, 2, 1): CFAType.GRBG,
                (1, 2, 0, 1): CFAType.GBRG,
            }

            key = tuple(pattern.flatten())
            cfa_type = mapping.get(key, CFAType.NONE)

        with open(str(path), 'rb') as f:
            exif_data = exifread.process_file(f)
        return AstroImage(
            info=AstroImageInfo(
                path=path,
                shape=ImageShape(width=width, height=height, channels=channels),
                color_mode= ColorMode.BAYER,
                cfa_type=cfa_type,
                bit_depth=raw.raw_image.dtype.itemsize * 8,
                f_number=exif_data.get('EXIF FNumber').values[0].num / exif_data.get('EXIF FNumber').values[0].den if 'EXIF FNumber' in exif_data else None,
                exposure_time=exif_data.get('EXIF ExposureTime').values[0].num / exif_data.get('EXIF ExposureTime').values[0].den if 'EXIF ExposureTime' in exif_data else None,
                iso=exif_data.get('EXIF ISOSpeedRatings').values[0] if 'EXIF ISOSpeedRatings' in exif_data else None,
                exif={tag: str(value) for tag, value in exif_data.items()}
            ),
            image=None
        )
    

def load_raw_image(path: Path) -> np.ndarray:
    """Load RAW image pixel data.
    
    Args:
        path: Path to RAW file
        
    Returns:
        Raw image data as float32 numpy array
    """
    with rawpy.imread(str(path)) as raw:
        data = raw.raw_image.astype(np.float32)

        if data.ndim == 2:
            data = data[..., np.newaxis]
        return data