from ..alignment.transform import AlignedFrameProvider, ImageTransformer
from ..core.frame_provider import FrameProvider
from ..stacking.combiner import ImageCombiner
from ..project.project import Project
from ..project.settings import StackingSettings
from ..utils.timer import timer


class StackingPipeline:
    def __init__(self, provider: FrameProvider):
        self.provider = provider

    def run(self, project: Project, settings: StackingSettings, progress=None, is_cancelled=None) -> None:
        provider = self.provider
        if project.settings.use_alignment:
            provider = AlignedFrameProvider(provider, ImageTransformer())

        with timer("StackWorkers", True):
            combiner = ImageCombiner(provider)

            result = combiner.combine(
                project.light_frames,
                settings.method,
                progress=progress,
                is_cancelled=is_cancelled,
                combine_msg="スタック後画像"
            )

            project.result.stacked_image = result
            return 