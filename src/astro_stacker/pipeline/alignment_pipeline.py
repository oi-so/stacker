from ..core.provider import FrameProvider
from ..project.project import Project
from ..project.settings import AlignmentSettings
from ..stars.detector import detect_stars
from ..alignment.aligner import align_catalogs
from ..io.image_data import TransformData, AlignmentData
import logging

logger = logging.getLogger(__name__)


class AlignmentPipeline:
    def __init__(self, provider: FrameProvider) -> None:
        self.provider = provider


    def run(self, project: Project, settings: AlignmentSettings, progress=None, is_cancelled=None):
        if not project.light_frames:
            raise ValueError("No light frames")


        light_frames = [
            frame for frame in project.light_frames
            if frame.info.enabled
        ]
        total = len(light_frames)

        if project.reference_image is None:
            project.reference_image = (
                light_frames[
                    len(light_frames) // 2
                ]
            )

        if progress:
            progress("位置合わせ", 1, total, project.reference_image.info.path.name)

        reference = project.reference_image
        reference_image = self.provider.get_image(reference)
        reference_catalog = detect_stars(reference_image, sigma=settings.sigma)
        reference_catalog.stars = reference_catalog.brightest(settings.max_stars)
        
        
        is_finished_astro_image = False
        for i, astro_image in enumerate(light_frames, 2):
            if astro_image is reference:
                astro_image.info.transform = TransformData()
                astro_image.info.alignment_data = AlignmentData()
                is_finished_astro_image = True
                continue

            if is_cancelled and is_cancelled(): return
            if progress:
                finished_frame_count = i - (1 if is_finished_astro_image else 0)
                progress("位置合わせ", finished_frame_count, total, astro_image.info.path.name)


            image = self.provider.get_image(astro_image)
            catalog = detect_stars(image, sigma=settings.sigma)
            catalog.stars = catalog.brightest(settings.max_stars)
            result = align_catalogs(reference_catalog, catalog)
            astro_image.info.transform = result.transform
            astro_image.info.alignment_data = result.info
            logger.info(
                "Aligned %s: matched=%s rms=%.3f",
                astro_image.info.path.name,
                result.info.matched_star_count,
                result.info.rms_error or 0.0,
            )
