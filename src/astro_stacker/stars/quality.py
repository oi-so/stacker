"""Image quality evaluation based on star detection and FWHM."""

import numpy as np
from ..io.image_data import ScoreData
from .detector import detect_stars
from .fwhm import measure_fwhm
from astropy.stats import sigma_clipped_stats



class QualityAnalyzer:
    """Analyze image quality using star metrics.
    
    Computes a quality score based on:
    - Number of detected stars
    - Median FWHM of stars (lower is better)
    - Background noise level
    
    Formula: score = star_count / (fwhm + 1e-6)
    """
    
    def analyze(self, image: np.ndarray, use_star_count_max: int = 50) -> ScoreData:
        """Analyze image quality.
        
        Args:
            image: Input image array
            use_star_count_max: Maximum number of stars to measure FWHM for
            
        Returns:
            ScoreData with quality metrics
        """
        catalog = detect_stars(image)
        star_count = len(catalog.stars)
        top_catalog = catalog.brightest(use_star_count_max)
        
        # Measure FWHM for brightest stars
        fwhms = np.array([measure_fwhm(image, c) for c in top_catalog])
        fwhms = fwhms[fwhms != None]  # Remove None values
        
        median_fwhm = float(np.median(fwhms)) if len(fwhms) > 0 else 0.0
        _, _, background_noise = sigma_clipped_stats(image)
        
        # Quality score: more stars and smaller FWHM = higher score
        score = star_count / (median_fwhm + 1e-6)

        return ScoreData(
            score=score,
            star_count=star_count,
            fwhm=median_fwhm,
            background_noise=float(background_noise)
        )