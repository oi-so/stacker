from ..alignment.transform import AlignedFrameProvider, ImageTransformer
from ..core.frame_provider import FrameProvider
from ..moving_object.provider import MovingObjectAlignedFrameProvider
from ..moving_object.transform import MovingObjectTransformBuilder
from ..project.project import Project
from ..project.settings import StackingSettings
from ..stacking.combiner import ImageCombiner
from ..utils.timer import timer


class StackingPipeline:
    def __init__(self, provider: FrameProvider):
        self.provider = provider

    def run(self, project: Project, settings: StackingSettings, progress=None, is_cancelled=None) -> None:
        provider = self.provider
        moving_object = project.settings.moving_object
        if moving_object.enabled:
            if not project.settings.use_alignment:
                raise ValueError("移動天体基準スタックには星基準の位置合わせが必要です。")
            if project.reference_image is None:
                raise ValueError("位置合わせの参照画像が設定されていません。")

            enabled_frames = [frame for frame in project.light_frames if frame.info.enabled]
            target_reference_frame = project.reference_image
            if moving_object.reference_frame_path is not None:
                target_reference_frame = next(
                    (
                        frame
                        for frame in enabled_frames
                        if frame.info.path == moving_object.reference_frame_path
                    ),
                    None,
                )
                if target_reference_frame is None:
                    raise ValueError("移動天体基準として選択した画像が有効ではありません。")
            transform_builder = MovingObjectTransformBuilder(
                enabled_frames,
                project.reference_image,
                moving_object.anchors,
                target_reference_frame,
            )
            provider = MovingObjectAlignedFrameProvider(
                provider,
                ImageTransformer(),
                transform_builder,
            )
        elif project.settings.use_alignment:
            provider = AlignedFrameProvider(provider, ImageTransformer())

        frames = [
            frame for frame in project.light_frames
            if frame.info.enabled and (not project.settings.use_alignment or frame.info.is_aligned)
        ]

        if not frames:
            raise ValueError("No light frames available for stacking")


        with timer("StackWorkers", True):
            combiner = ImageCombiner(provider)

            result = combiner.combine(
                frames,
                settings.method,
                settings,
                progress=progress,
                is_cancelled=is_cancelled,
                combine_msg="スタック後画像"
            )

            project.result.stacked_image = result
            return
