from pathlib import Path
import numpy as np

from .image_data import AstroImage
from .fits_loader import load_fits_image, load_fits_info
from .raw_loader import load_raw_image, load_raw_info
from .standard_loader import load_standard_image, load_standard_info

RAW_EXTENSIONS = {
    '.cr2', '.nef', '.arw', '.dng', '.rw2', '.orf', '.raf', '.pef', '.srw',
    '.srf', '.sr2', '.kdc', '.mos', '.mrw', '.mef', '.erf', '.x3f',
    '.bay', '.cap', '.iiq', '.rwl', '.raw'
}
FITS_EXTENSIONS = {'.fits', '.fit', '.fts'}
JPEG_EXTENSIONS = {'.jpg', '.jpeg'}
PING_EXTENSIONS = {'.png'}

def load_info(path: Path) -> AstroImage:
    ext = path.suffix.lower()
    if ext in RAW_EXTENSIONS:
        return load_raw_info(path)
    elif ext in FITS_EXTENSIONS:
        return load_fits_info(path)

    return load_standard_info(path)


def load_image(path: Path) -> np.ndarray:
    ext = path.suffix.lower()
    if ext in RAW_EXTENSIONS:
        return load_raw_image(path)
    elif ext in FITS_EXTENSIONS:
        return load_fits_image(path)

    return load_standard_image(path)