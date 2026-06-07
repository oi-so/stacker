"""FITS image format loader.

Loads FITS files with support for WCS (World Coordinate System) information
and various FITS array shapes.
"""

from astropy.io import fits
import numpy as np
from pathlib import Path
import exifread
from typing import cast
from astropy.io.fits import PrimaryHDU
from astropy.wcs import WCS

from .image_data import AstroImageInfo, AstroImage, WCSData, ImageShape



def load_fits_info(path: Path) -> AstroImage:
    """Load FITS image metadata including WCS if available.
    
    Args:
        path: Path to FITS file
        
    Returns:
        AstroImage with metadata, image data is None
        
    Raises:
        ValueError: If FITS array has unsupported shape
    """
    with fits.open(path) as hdul:
        hud = cast(PrimaryHDU, hdul[0])
        header = hud.header
        shape = hud.shape
    
    # Handle different array shapes (2D, 3D with different axis orders)
    if len(shape) == 2:
        height, width = shape
        channels = 1
    elif len(shape) == 3:
        # Heuristic: if first dimension is small, it's likely channels
        if len(str(shape[0])) <= 4:
            channels, height, width = shape
        else:
            height, width, channels = shape
    else: raise ValueError(f"Unsupported FITS image shape: {shape}")

    # Extract FITS header keywords
    exposure_time = header.get('EXPTIME')
    iso = header.get('ISO')
    f_number = header.get('FNUMBER')
    bit_depth = header.get("BITPIX")
    bit_depth = abs(int(bit_depth)) if bit_depth is not None else 16
    
    # Try to extract WCS if available
    try:
        wcs = WCS(header)
    except:
        wcs = None

    info = AstroImageInfo(
        path=path,
        shape=ImageShape(
            width=width,
            height=height,
            channels=channels
        ),
        bit_depth=bit_depth,
        exposure_time=header.get('EXPTIME'),
        iso=header.get('ISO'),
        f_number=header.get('FNUMBER'),
        exif=dict(header),
        wcs=wcs
    )
    return AstroImage(info=info, image=None) 


def load_fits_image(path: Path) -> np.ndarray:
    """Load FITS image pixel data.
    
    Args:
        path: Path to FITS file
        
    Returns:
        Pixel data as float32 numpy array
        
    Raises:
        ValueError: If no image data found in FITS file
    """
    data = fits.getdata(path)

    if data is None:
        raise ValueError(
            f"No image data found in {path}"
        )

    # Convert 2D array to 3D with channel dimension
    if data.ndim == 2:
        data = data[..., np.newaxis]

    # Handle different 3D axis orders
    elif data.ndim == 3:
        if data.shape[0] <= 4:
            # Likely channels-first, move to channels-last
            data = np.moveaxis(data, 0, -1)

    return np.asarray(
        data,
        dtype=np.float32
    )
