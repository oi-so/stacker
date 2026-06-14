from ..io.image_manager import ImageManager
from ..core.provider import ImageManagerProvider, DebayerFrameProvider
from ..calibration.provider import CalibratedFrameProvider
from ..project.project import Project
from ..project.settings import DebayerTiming
from ..calibration.calibration import MasterFrameBuilder, Calibrator
from ..pipeline.alignment_pipeline import AlignmentPipeline
from ..pipeline.stacking_pipeline import StackingPipeline


# TODO:将来的にProject内に入れて切り替えれるようにするかも
CALIBRATE_BEFORE_ALIGN: bool = True


class ProcessingPipeline:
    def __init__(self, manager: ImageManager):
        self.manager = manager


    def _build_master_frames(self, project: Project, builder: MasterFrameBuilder) -> None:
        if project.calibration_frames.darks:
            project.master_calibration_frames.dark = builder.build(
                project.calibration_frames.darks,
                project.settings.dark_frame.method
            )

        if project.calibration_frames.flats:
            project.master_calibration_frames.flat = builder.build(
                project.calibration_frames.flats,
                project.settings.flat_frame.method
            )

        if project.calibration_frames.biases:
            project.master_calibration_frames.bias = builder.build(
                project.calibration_frames.biases,
                project.settings.bias_frame.method
            )

        if project.calibration_frames.flat_darks:
            project.master_calibration_frames.flat_dark = builder.build(
                project.calibration_frames.flat_darks,
                project.settings.flat_dark_frame.method
            )


    def run(self, project: Project) -> None:
        provider = ImageManagerProvider(self.manager)
        builder = MasterFrameBuilder(provider)

        self._build_master_frames(project, builder)

        calibrator = Calibrator(project, project.settings.calibration)
        if CALIBRATE_BEFORE_ALIGN:
            provider = CalibratedFrameProvider(provider, calibrator)

        
        alignment_pipeline = AlignmentPipeline(provider)
        alignment_pipeline.run(project, project.settings.alignment)

        if not CALIBRATE_BEFORE_ALIGN:
            provider = CalibratedFrameProvider(provider, calibrator)

        stack_provider = provider

        # TODO:現時点ではスタック後ディベイヤーはスタック処理がディベイヤー前非対応なのでできないため直す
        if project.settings.debayer_timing == DebayerTiming.BEFORE_STACK:
            stack_provider = DebayerFrameProvider(stack_provider)

        stacking_pipeline = StackingPipeline(stack_provider)
        stacking_pipeline.run(project, project.settings.light_frame)

