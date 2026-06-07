import numpy as np
from ..io.image_data import ScoreData
from .detector import detect_stars
from .fwhm import measure_fwhm
from astropy.stats import sigma_clipped_stats



class QualityAnalyzer:
    def analyze(self, image: np.ndarray, use_star_count_max: int = 50) -> ScoreData:
        catalog = detect_stars(image)
        star_count = len(catalog.stars)
        top_catalog = catalog.brightest(use_star_count_max)
        fwhms = np.array([measure_fwhm(image, c) for c in top_catalog])
        fwhms = fwhms[fwhms != None]
        median_fwhm = float(np.median(fwhms))
        _, _, background_noise = sigma_clipped_stats(image)
        score = star_count / (median_fwhm + 1e-6)


        return ScoreData(
            score=score,
            star_count=star_count,
            fwhm=median_fwhm,
            background_noise=float(background_noise)
        )