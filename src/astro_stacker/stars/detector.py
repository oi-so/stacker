"""Star detection using photometry-based methods."""

import numpy as np
from astropy.stats import SigmaClip, sigma_clipped_stats
from photutils.background import Background2D, MedianBackground
from photutils.detection import DAOStarFinder

from .star_data import Star, StarCatalog


def to_luminance(image):
    if image.ndim == 2:
        return image

    if image.shape[2] == 1:
        return image[..., 0]

    return image.mean(axis=2)


def background_stats(image: np.ndarray):
    """Estimate a single *global* background level from a spatial grid
    of at most 512² pixels. Kept for quick quality/noise reporting only
    -- star detection itself uses `local_background`, since a single
    global value badly underestimates the sky level inside bright,
    extended nebulosity.
    """
    image = to_luminance(image)
    sy = max(1, (image.shape[0] + 511) // 512)
    sx = max(1, (image.shape[1] + 511) // 512)
    sy += (sy % 2 == 0)
    sx += (sx % 2 == 0)
    return sigma_clipped_stats(image[::sy, ::sx])


def local_background(image: np.ndarray, box_size: int = 64, filter_size: int = 3):
    """Estimate a spatially-varying background/RMS map.

    A single global median/std badly underestimates the local sky level
    in and around bright, extended nebulosity (e.g. the Trapezium/M42
    core). Every bit of nebula texture then exceeds ``sigma *
    global_std`` and DAOStarFinder reports it as a "star" -- this is
    what produces the dense cluster of false detections seen in HDR's
    darker sub-exposures. Background2D fits the background per tile, so
    the effective threshold rises inside bright nebulosity and only
    genuinely star-like peaks survive.
    """
    image = to_luminance(image)
    box = max(8, min(box_size, max(8, min(image.shape) // 3)))
    bkg = Background2D(
        image,
        box_size=box,
        filter_size=filter_size,
        sigma_clip=SigmaClip(sigma=3.0),
        bkg_estimator=MedianBackground(),
        exclude_percentile=50.0,
    )
    return bkg.background, bkg.background_rms


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

    try:
        background, _ = local_background(image)
        residual = image - background
    except Exception:
        # Fall back to the old global estimate if Background2D can't
        # cope with this frame (e.g. too small / mostly masked).
        _, median, _ = background_stats(image)
        residual = image - median

    _, _, std = sigma_clipped_stats(residual)

    finder = DAOStarFinder(
        fwhm=fwhm,
        threshold=sigma * std,
    )

    sources = finder(residual)
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