from PIL import Image
import numpy as np
from pathlib import Path
import exifread

from .image_data import AstroImageInfo, AstroImage, ImageShape


def load_standard_info(path: Path) -> AstroImage:
    with Image.open(path) as img:
        width, height = img.size
        mode = img.mode
        dtype = np.uint8 if mode in ['L', 'RGB'] else np.float32
        with open(path, 'rb') as f:
            exif_data = exifread.process_file(f)
        return AstroImage(
            info=AstroImageInfo(
                path=path,
                shape=ImageShape(width=width, height=height, channels=len(img.getbands()) if img.getbands() else 1),
                bit_depth=8 if dtype == np.uint8 else 32,
                f_number=exif_data.get('EXIF FNumber').values[0].num / exif_data.get('EXIF FNumber').values[0].den if 'EXIF FNumber' in exif_data else None,
                exposure_time=exif_data.get('EXIF ExposureTime').values[0].num / exif_data.get('EXIF ExposureTime').values[0].den if 'EXIF ExposureTime' in exif_data else None,
                iso=exif_data.get('EXIF ISOSpeedRatings').values[0] if 'EXIF ISOSpeedRatings' in exif_data else None,
                exif={tag: str(value) for tag, value in exif_data.items()}
            ),
            data=None
        )
    

def load_standard_image(path: Path) -> np.ndarray:
    with Image.open(path) as img:
        img = img.convert('RGB')  # Ensure image is in RGB format
        data = np.array(img)
        return data
