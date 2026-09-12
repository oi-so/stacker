"""Star detection using photometry-based methods."""

import numpy as np
from astropy.stats import sigma_clipped_stats
from photutils.detection import DAOStarFinder

from .star_data import Star, StarCatalog


def to_luminance(image):
    if image.ndim == 2:
        return image

    if image.shape[2] == 1:
        return image[..., 0]

    return image.mean(axis=2)


def background_stats(image: np.ndarray):
    """Estimate the background from a spatial grid of at most 512² pixels."""
    image = to_luminance(image)
    sy = max(1, (image.shape[0] + 511) // 512)
    sx = max(1, (image.shape[1] + 511) // 512)
    # Odd strides sample both phases of a Bayer mosaic.
    sy += (sy % 2 == 0)
    sx += (sx % 2 == 0)
    return sigma_clipped_stats(image[::sy, ::sx])


def detect_stars(image: np.ndarray, fwhm: float = 4.0, sigma: float = 5.0) -> StarCatalog:
    """
    Search stars and return stars catalog.
    
    Parameters
    ----------
    image: np.ndarray
        Image which will be searched
    fwhm: float
        Finding star size
    sigma: float
        Finding star brightness
    """
    image = to_luminance(image)
    _, median, std = background_stats(image)

    finder = DAOStarFinder(
        fwhm=fwhm,
        threshold=sigma * std,
        sharpness_range=(0.2, 1.0),
        roundness_range=(-0.5, 0.5),
    )

    sources = finder(image - median)
    if sources is None:
        return StarCatalog([])

    stars = []

    for row in sources:
        stars.append(
            Star(
                x=float(row["x_centroid"]),
                y=float(row["y_centroid"]),
                flux=float(row["flux"]),
                peak=float(row["peak"]),
                sharpness=float(row["sharpness"]),
                roundness=float(row["roundness1"]),
                # TODO: 仮の楕円率
                ellipticity=abs(float(row["roundness1"])),
            )
        )

    return StarCatalog(stars)