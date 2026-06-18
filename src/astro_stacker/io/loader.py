"""Unified image loading for multiple file formats.

Supports RAW, FITS, JPEG, PNG, TIFF formats with automatic format detection.
Provides both metadata loading (fast) and pixel data loading (memory-intensive).
"""

from pathlib import Path
import numpy as np
import logging

from .image_data import AstroImage
from .fits_loader import load_fits_image, load_fits_info
from .raw_loader import load_raw_image, load_raw_info
from .standard_loader import load_standard_image, load_standard_info

# File extension sets for each loader
RAW_EXTENSIONS = {
    '.cr2', '.nef', '.arw', '.dng', '.rw2', '.orf', '.raf', '.pef', '.srw',
    '.srf', '.sr2', '.kdc', '.mos', '.mrw', '.mef', '.erf', '.x3f',
    '.bay', '.cap', '.iiq', '.rwl', '.raw'
}
FITS_EXTENSIONS = {'.fits', '.fit', '.fts'}

# Mapping of loader type to (extensions, info_loader, image_loader)
LOADERS = {
    'raw': (RAW_EXTENSIONS, load_raw_info, load_raw_image),
    'fits': (FITS_EXTENSIONS, load_fits_info, load_fits_image),
}

logger = logging.getLogger(__name__)


def load_info(path: Path) -> AstroImage:
    """Load image metadata without loading pixel data.
    
    Args:
        path: Path to image file
        
    Returns:
        AstroImage with metadata filled in, image data set to None
        
    Note:
        Tries RAW and FITS loaders first, then falls back to standard loader
        (PNG, JPEG, TIFF, etc.)
    """
    path = Path(path)
    ext = path.suffix.lower()
    for loader_name, (extensions, info_loader, image_loader) in LOADERS.items():
        if ext in extensions:
            logger.debug("Loading %s metadata with %s loader", path, loader_name)
            return info_loader(path)
    logger.debug("Loading %s metadata with standard loader", path)
    return load_standard_info(path)


def load_image(astro_image: AstroImage) -> np.ndarray:
    """Load pixel data for an image.
    
    Args:
        astro_image: AstroImage object with info.path set
        
    Returns:
        Pixel data as numpy array
    """
    path = astro_image.info.path
    ext = path.suffix.lower()
    for loader_name, (extensions, info_loader, image_loader) in LOADERS.items():
        if ext in extensions:
            image = image_loader(path)
            break
    else:
        image = load_standard_image(path)

    image = np.asarray(image, dtype=np.float32)
    return np.clip(image, 0, None)
