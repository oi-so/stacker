from dataclasses import dataclass

from ..core.frame_provider import FrameProvider
from ..io.image_data import AstroImage, ScoreData
from ..stars.detector import detect_stars
from ..stars.quality import QualityAnalyzer
from ..stars.star_data import StarCatalog


@dataclass
class DetectionResult:
    catalog: StarCatalog
    alignment_catalog: StarCatalog
    score_data: ScoreData



def process_frame(
    provider: FrameProvider,
    frame: AstroImage,
    sigma: float,
    max_stars: int,
    star_fwhm: float = 4.0,
    alignment_sharpness_min: float = 0.20,
    alignment_roundness_max: float = 0.50,
):
    # Only providers that describe their input may reuse measurements.
    # Calibrated/transformed providers intentionally recompute them.
    key = None
    token = getattr(provider, "cache_token", None)
    if token is not None:
        key = (
            token(frame), sigma, max_stars, star_fwhm,
            alignment_sharpness_min, alignment_roundness_max,
        )
        cached = getattr(frame, "_detection_cache", None)
        if cached is not None and cached[0] == key:
            return cached[1]
    analyzer = QualityAnalyzer()

    image = provider.get_image(frame)

    catalog = detect_stars(image, fwhm=star_fwhm, sigma=sigma)
    alignment_catalog = catalog.point_sources(
        max_stars,
        minimum_sharpness=alignment_sharpness_min,
        maximum_abs_roundness=alignment_roundness_max,
        width=frame.info.shape.width,
        height=frame.info.shape.height,
    )

    try:
        score = analyzer.analyze_catalog(
            image,
            catalog,
            max_stars,
        )
    except Exception:
        score = ScoreData()

    result = DetectionResult(
        catalog,
        alignment_catalog,
        score,
    )
    if key is not None:
        frame._detection_cache = (key, result)
    return result
