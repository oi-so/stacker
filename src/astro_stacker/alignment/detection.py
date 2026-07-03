from dataclasses import dataclass
from ..io.image_data import ScoreData, AstroImage
from ..stars.star_data import StarCatalog
from ..core.frame_provider import FrameProvider
from ..stars.quality import QualityAnalyzer
from ..stars.detector import detect_stars



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
):
    analyzer = QualityAnalyzer()

    image = provider.get_image(frame)

    catalog = detect_stars(image, sigma=sigma)
    alignment_catalog = catalog.brightest(max_stars)

    try:
        score = analyzer.analyze_catalog(
            image,
            catalog,
            max_stars,
        )
    except Exception:
        score = ScoreData()

    return DetectionResult(
        catalog,
        alignment_catalog,
        score,
    )