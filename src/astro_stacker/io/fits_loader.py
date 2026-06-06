from astropy.io import fits
import numpy as np
from pathlib import Path
import exifread
from typing import cast
from astropy.io.fits import PrimaryHDU
from astropy.wcs import WCS

from .image_data import AstroImageInfo, AstroImage, WCSData, ImageShape



def load_fits_info(path: Path) -> AstroImage:
    """
    Load FITS image metadata and return an `AstroImage` with the metadata filled in without the image data.
    """
    with fits.open(path) as hdul:
        hud = cast(PrimaryHDU, hdul[0])
        header = hud.header
        shape = hud.shape
    
    if len(shape) == 2:
        height, width = shape
        channels = 1
    elif len(shape) == 3:
        if len(str(shape[0])) <= 4:
            channels, height, width = shape
        else:
            height, width, channels = shape
    else: raise ValueError(f"Unsupported FITS image shape: {shape}")

    exposure_time = header.get('EXPTIME')
    iso = header.get('ISO')
    f_number = header.get('FNUMBER')
    bit_depth = header.get("BITPIX")
    bit_depth = abs(int(bit_depth)) if bit_depth is not None else 16
    wcs = WCS(header)

    info = AstroImageInfo(
        path=path,
        shape=ImageShape(
            width=width,
            height=height,
            channels=channels
        ),
        bit_depth=bit_depth,  # FITS images are often 16-bit, but this can vary
        exposure_time=header.get('EXPTIME'),
        iso=header.get('ISO'),
        f_number=header.get('FNUMBER'),
        exif=dict(header),
        wcs=wcs
    )
    return AstroImage(info=info, image=None) 


def load_fits_image(path: Path) -> np.ndarray:
    """Load FITS image data as a NumPy array"""

    data = fits.getdata(path)

    if data is None:
        raise ValueError(
            f"No image data found in {path}"
        )

    if data.ndim == 2:
        data = data[..., np.newaxis]

    elif data.ndim == 3:
        if data.shape[0] <= 4:
            data = np.moveaxis(data, 0, -1)

    return np.asarray(
        data,
        dtype=np.float32
    )
