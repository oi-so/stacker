from ..core.provider import FrameProvider
from ..project.project import Project
from ..project.settings import AlignmentSettings
from ..stars.detector import detect_stars
from ..alignment.aligner import align_catalogs
from ..io.image_data import TransformData



class AlignmentPipeline:
    def __init__(self, provider: FrameProvider) -> None:
        self.provider = provider


    def run(self, project: Project, settings: AlignmentSettings):
        if not project.light_frames:
            raise ValueError("No light frames")

        if project.reference_image is None:
            project.reference_image = (
                project.light_frames[
                    len(project.light_frames) // 2
                ]
            )

        reference = project.reference_image
        reference_image = self.provider.get_image(reference)
        reference_catalog = detect_stars(reference_image)
        
        
        for astro_image in project.light_frames:
            if astro_image is reference:
                astro_image.info.transform = TransformData()
                continue

            image = self.provider.get_image(astro_image)
            catalog = detect_stars(image)
            result = align_catalogs(reference_catalog, catalog)
            astro_image.info.transform = result.transform
            astro_image.info.alignment_data = result.info
