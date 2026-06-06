import rawpy
import numpy as np
from pathlib import Path
import exifread
from .image_data import AstroImageInfo, AstroImage, ImageShape


def load_raw_info(path: Path) -> AstroImage:
    with rawpy.imread(str(path)) as raw:
        height, width = raw.sizes.height, raw.sizes.width
        channels = raw.raw_colors
        with open(str(path), 'rb') as f:
            exif_data = exifread.process_file(f)
        return AstroImage(
            info=AstroImageInfo(
                path=path,
                shape=ImageShape(width=width, height=height, channels=channels),
                bit_depth=raw.raw_image.dtype.itemsize * 8,
                f_number=exif_data.get('EXIF FNumber').values[0].num / exif_data.get('EXIF FNumber').values[0].den if 'EXIF FNumber' in exif_data else None,
                exposure_time=exif_data.get('EXIF ExposureTime').values[0].num / exif_data.get('EXIF ExposureTime').values[0].den if 'EXIF ExposureTime' in exif_data else None,
                iso=exif_data.get('EXIF ISOSpeedRatings').values[0] if 'EXIF ISOSpeedRatings' in exif_data else None,
                exif={tag: str(value) for tag, value in exif_data.items()}
            ),
            image=None
        )
    

def load_raw_image(path: Path) -> np.ndarray:
    with rawpy.imread(str(path)) as raw:
        data = raw.raw_image.astype(np.float32)
        return data