"""Star-catalog based soft mask generation."""

import cv2
import numpy as np

from ..project.settings import StarMaskSettings
from ..stars.star_data import StarCatalog


def generate_star_mask(
    shape: tuple[int, int],
    catalog: StarCatalog,
    settings: StarMaskSettings | None = None,
) -> np.ndarray:
    settings = settings or StarMaskSettings()
    mask = np.zeros(shape, dtype=np.float32)
    stars = [star for star in catalog.stars if star.flux >= settings.minimum_flux]
    positive_flux = [max(float(star.flux), 0.0) for star in stars]
    flux_reference = float(np.median(positive_flux)) if positive_flux else 1.0
    flux_reference = max(flux_reference, 1e-8)

    for star in stars:
        fwhm = max(float(star.fwhm or 1.0), 0.5)
        brightness = np.log1p(max(float(star.flux), 0.0) / flux_reference)
        halo = settings.bright_star_scale * brightness if settings.include_halos else 0.0
        radius = max(0.5, fwhm * settings.radius_scale * (1.0 + halo) + settings.expansion)
        if settings.elliptical:
            ellipticity = float(np.clip(star.ellipticity or 0.0, 0.0, 0.95))
            axes = (max(1, round(radius)), max(1, round(radius * (1.0 - ellipticity))))
        else:
            axes = (max(1, round(radius)), max(1, round(radius)))
        cv2.ellipse(
            mask, (round(star.x), round(star.y)), axes, 0.0, 0.0, 360.0, 1.0, -1
        )

    if settings.feather > 0:
        sigma = float(settings.feather)
        mask = cv2.GaussianBlur(mask, (0, 0), sigmaX=sigma, sigmaY=sigma)
        peak = float(mask.max())
        if peak > 0:
            mask /= peak
    np.clip(mask, 0.0, 1.0, out=mask)
    return 1.0 - mask if settings.inverted else mask
