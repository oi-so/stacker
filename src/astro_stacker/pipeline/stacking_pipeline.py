from ..alignment.transform import AlignedFrameProvider, ImageTransformer
from ..core.provider import FrameProvider
from ..stacking.combiner import ImageCombiner
from ..project.project import Project
from ..project.settings import StackingSettings


class StackingPipeline:
    def __init__(self, provider: FrameProvider):
        self.provider = provider

    def run(self, project: Project, settings: StackingSettings) -> None:
        aligned_provider = AlignedFrameProvider(self.provider, ImageTransformer())

        combiner = ImageCombiner(aligned_provider)

        result =  combiner.combine(
            project.light_frames,
            settings.method
        )

        project.result.stacked_image = result
        return 