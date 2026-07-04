"""RAW image format loader.

Loads RAW files from digital cameras using rawpy.
"""

import rawpy
import numpy as np
from pathlib import Path
import exifread
from .image_data import AstroImageInfo, AstroImage, ImageShape
from .image_data import ColorMode, CFAType

RAW_POSTPROCESS_KWARGS = {
    "no_auto_bright": True,
    "bright": 1.0,
    "use_camera_wb": False,
    "use_auto_wb": False,
    "output_bps": 16,
    "gamma": (1, 1),
}


def load_raw_info(path: Path) -> AstroImage:
    """Load RAW image metadata.
    
    Args:
        path: Path to RAW file
        
    Returns:
        AstroImage with metadata from RAW header and EXIF
    """
    with rawpy.imread(str(path)) as raw:
        height, width = raw.sizes.height, raw.sizes.width
        channels = 1

        pattern = raw.raw_pattern
        if pattern is None:
            raise ValueError("pattern is None")
        pattern = pattern.copy()
        pattern[pattern == 3] = 1
        key = tuple(pattern.flatten())
        cfa_type = CFAType.NONE

        mapping = {
            (0, 1, 1, 2): CFAType.RGGB,
            (2, 1, 1, 0): CFAType.BGGR,
            (1, 0, 2, 1): CFAType.GRBG,
            (1, 2, 0, 1): CFAType.GBRG,
        }
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
                iso=int(exif_data.get('EXIF ISOSpeedRatings').values[0]) if 'EXIF ISOSpeedRatings' in exif_data else None,
                exif={tag: str(value) for tag, value in exif_data.items()}
            )
        )
    

def load_raw_image(path: Path) -> np.ndarray:
    """Load RAW image pixel data.
    
    Args:
        path: Path to RAW file
        
    Returns:
        Raw image data as float32 numpy array
    """
    with rawpy.imread(str(path)) as raw:
        # Keep RAW frames as the camera's linear Bayer plane. This is the
        # safest policy for dark/bias/flat calibration because no per-frame
        # auto-brightening, white balance, or gamma is introduced.
        data = raw.raw_image_visible.astype(np.float32, copy=True)

        if data.ndim == 2:
            data = data[..., np.newaxis]
        return np.clip(data, 0, None)


def load_raw_rgb_image(path: Path) -> np.ndarray:
    """Load demosaiced linear RGB data with deterministic rawpy settings."""
    with rawpy.imread(str(path)) as raw:
        try:
            import rawpy as _rawpy

            kwargs = {
                **RAW_POSTPROCESS_KWARGS,
                "demosaic_algorithm": _rawpy.DemosaicAlgorithm.AHD,
            }
        except Exception:
            kwargs = RAW_POSTPROCESS_KWARGS
        data = raw.postprocess(**kwargs)
    return np.clip(data.astype(np.float32), 0, None)
