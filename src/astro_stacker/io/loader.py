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


LOADERS = {
    'raw': (RAW_EXTENSIONS, load_raw_info, load_raw_image),
    'fits': (FITS_EXTENSIONS, load_fits_info, load_fits_image),
}


def load_info(path: Path) -> AstroImage:
    ext = path.suffix.lower()
    for loader_name, (extensions, info_loader, image_loader) in LOADERS.items():
        if ext in extensions:
            return info_loader(path)
    return load_standard_info(path)


def load_image(astro_image: AstroImage) -> np.ndarray:
    path = astro_image.info.path
    ext = path.suffix.lower()
    for loader_name, (extensions, info_loader, image_loader) in LOADERS.items():
        if ext in extensions:
            return image_loader(path)
    return load_standard_image(path)