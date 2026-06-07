"""Star detection using photometry-based methods."""

import numpy as np

from astropy.stats import sigma_clipped_stats

from photutils.detection import DAOStarFinder

from .star_data import Star, StarCatalog




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

    _, median, std = sigma_clipped_stats(image)

    finder = DAOStarFinder(
        fwhm=fwhm,
        threshold=sigma * std
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
                roundness=float(row["roundness1"])
            )
        )

    return StarCatalog(stars)