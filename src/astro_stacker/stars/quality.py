"""Image quality evaluation based on star detection and FWHM."""

import numpy as np
from ..io.image_data import ScoreData
from .fwhm import measure_fwhm
from ..stars.star_data import StarCatalog
from astropy.stats import sigma_clipped_stats



class QualityAnalyzer:
    """Analyze image quality using star metrics.
    
    Computes a quality score based on:
    - Number of detected stars
    - Median FWHM of stars (lower is better)
    - Background noise level
    
    Formula: score = star_count / (fwhm + 1e-6)
    """
    
    def analyze_catalog(self, image: np.ndarray, catalog: StarCatalog, use_star_count_max: int):
        star_count = len(catalog.stars)
        top_catalog = catalog.brightest(use_star_count_max).stars

        # Measure FWHM for brightest stars
        fwhms = np.array([measure_fwhm(image, c) for c in top_catalog], dtype=object)
        # Filter out None values
        fwhms = np.array([f for f in fwhms if f is not None], dtype=np.float32)
        
        median_fwhm = float(np.median(fwhms)) if len(fwhms) > 0 else 0.0
        _, _, background_noise = sigma_clipped_stats(image)
        
        # Quality score: more stars and smaller FWHM = higher score
        score = star_count / (median_fwhm + 1e-6)

        ellipticities = [
            s.ellipticity
            for s in top_catalog
            if s.ellipticity is not None
        ]

        median_ellipticity = (
            float(np.median(ellipticities))
            if ellipticities
            else None
        )

        return ScoreData(
            score=score,
            star_count=star_count,
            fwhm=median_fwhm,
            ellipticity=median_ellipticity,
            background_noise=float(background_noise)
        )