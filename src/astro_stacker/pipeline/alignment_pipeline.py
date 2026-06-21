from ..core.provider import FrameProvider
from ..project.project import Project
from ..project.settings import AlignmentSettings, AlignmentMode
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
        
        enabled_frames = [
            frame for frame in project.light_frames
            if frame.info.enabled
        ]

        if project.reference_image is None:
            project.reference_image = (
                enabled_frames[
                    len(enabled_frames) // 2
                ]
            )
        
        if settings.mode == AlignmentMode.ALL:
            session_id = project.create_alignment_session()
        else:
            session_id = project.current_alignment_session_id
            if session_id is None:
                session_id = project.create_alignment_session()

        if settings.mode == AlignmentMode.ALL:
            frames_to_align = enabled_frames
        else:
            sessions = project.get_alignment_sessions()
            if len(sessions) > 1: 
                raise ValueError(
                    "異なる位置合わせグループが混在しています。\n"
                    "全て位置合わせを実行して下さい。"
                )

            frames_to_align = [
                frame
                for frame in enabled_frames
                if frame.info.alignment_session_id != session_id
            ]

        total = len(frames_to_align)
        if total == 0:
            logger.info("No frames need alignment")
            return


        reference = project.reference_image
        
        finished = 0
        if reference in frames_to_align:
            finished = 1
            if progress:
                progress("位置合わせ", finished, total, reference.info.path.name)

        reference.info.alignment_session_id = session_id
        reference.info.alignment_data = AlignmentData()
        reference.info.transform = TransformData()
        reference_image = self.provider.get_image(reference)
        reference_catalog = detect_stars(reference_image, sigma=settings.sigma)
        reference_catalog.stars = reference_catalog.brightest(settings.max_stars)

        for astro_image in frames_to_align:
            if astro_image is reference:
                continue

            finished += 1
            if is_cancelled and is_cancelled(): return
            if progress:
                progress("位置合わせ", finished, total, astro_image.info.path.name)

            image = self.provider.get_image(astro_image)
            catalog = detect_stars(image, sigma=settings.sigma)
            catalog.stars = catalog.brightest(settings.max_stars)
            result = align_catalogs(reference_catalog, catalog)
            astro_image.info.transform = result.transform
            astro_image.info.alignment_data = result.info
            astro_image.info.alignment_session_id = session_id
            logger.info(
                "Aligned %s: matched=%s rms=%.3f",
                astro_image.info.path.name,
                result.info.matched_star_count,
                result.info.rms_error or 0.0,
            )

        project.alignment_signature = project.make_alignment_signature()
