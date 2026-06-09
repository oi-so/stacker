import numpy as np

from ..alignment.aligner import align_catalogs
from ..alignment.transform import AlignedFrameProvider, ImageTransformer
from ..core.provider import FrameProvider
from ..stacking.combiner import ImageCombiner, Method
from ..project.project import Project
from ..project.settings import StackingSettings


class StackingPipeline:
    def __init__(self, provider: FrameProvider):
        self.provider = provider

    def run(self, project: Project, settings: StackingSettings) -> np.ndarray:
        aligned_provider = AlignedFrameProvider(self.provider, ImageTransformer())

        combiner = ImageCombiner(aligned_provider)

        return combiner.combine(
            project.light_frames,
            settings.method
        )