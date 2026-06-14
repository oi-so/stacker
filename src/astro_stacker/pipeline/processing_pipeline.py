from ..io.image_manager import ImageManager
from ..core.provider import ImageManagerProvider, DebayerFrameProvider, CalibratedFrameProvider
from ..project.project import Project
from ..project.settings import DebayerTiming
from ..calibration.calibration import MasterFrameBuilder, Calibrator
from ..pipeline.alignment_pipeline import AlignmentPipeline
from ..pipeline.stacking_pipeline import StackingPipeline

from ..io.saver import save_tiff
from pathlib import Path
import numpy as np

# TODO:将来的にProject内に入れて切り替えれるようにするかも
CALIBRATE_BEFORE_ALIGN: bool = True


class ProcessingPipeline:
    def __init__(self, manager: ImageManager):
        self.manager = manager


    def _build_master_frames(self, project: Project, builder: MasterFrameBuilder) -> None:
        use_bias = len(project.calibration_frames.biases) > 0 and project.settings.calibration.use_biases
        use_dark = len(project.calibration_frames.darks) > 0 and project.settings.calibration.use_darks
        use_flat = len(project.calibration_frames.flats) > 0 and project.settings.calibration.use_flats
        use_flat_dark = len(project.calibration_frames.flat_darks) > 0 and project.settings.calibration.use_flat_darks
        bias = None
        dark = None
        flat_dark = None
        flat = None

        if use_bias:
            bias = builder.build(
                project.calibration_frames.biases,
                project.settings.bias_frame.method
            )

        if use_dark:
            dark = builder.build(
                project.calibration_frames.darks,
                project.settings.dark_frame.method
            )
            if bias is not None:
                dark = dark - bias

        if use_flat_dark:
            flat_dark = builder.build(
                project.calibration_frames.flat_darks,
                project.settings.flat_dark_frame.method
            )
            if bias is not None:
                flat_dark = flat_dark - bias

        if use_flat:
            flat = builder.build(
                project.calibration_frames.flats,
                project.settings.flat_frame.method
            )
            if flat_dark is not None:
                flat = flat - flat_dark
            if bias is not None:
                flat = flat - bias

            flat = flat / np.mean(flat)

        project.master_calibration_frames.bias = bias
        project.master_calibration_frames.dark = dark
        project.master_calibration_frames.flat_dark = flat_dark
        project.master_calibration_frames.flat = flat

        if bias is not None and dark is not None:
            project.master_calibration_frames.sub_frame = dark + bias

        path = Path().cwd()
        save_tiff(project.master_calibration_frames.bias, path / "test_images" / "bias.tiff")
        save_tiff(project.master_calibration_frames.dark, path / "test_images" / "dark.tiff")
        save_tiff(project.master_calibration_frames.flat_dark, path / "test_images" / "flat_dark.tiff")
        save_tiff(project.master_calibration_frames.flat, path / "test_images" / "flat.tiff")
        save_tiff(project.master_calibration_frames.sub_frame, path / "test_images" / "sub.tiff")
        print(f"m_bias_max:{bias.max()}, m_dark:{dark.max()}, m_flat:{flat.max()}, m_flat_dark:{flat_dark.max()}")
        print(f"m_bias_min:{bias.min()}, m_dark:{dark.min()}, m_flat:{flat.min()}, m_flat_dark:{flat_dark.min()}")


    def run(self, project: Project) -> None:
        project.settings.calibration.use_biases = len(project.calibration_frames.biases) > 0
        project.settings.calibration.use_darks = len(project.calibration_frames.darks) > 0
        project.settings.calibration.use_flats = len(project.calibration_frames.flats) > 0
        project.settings.calibration.use_flat_darks = len(project.calibration_frames.flat_darks) > 0

        provider = ImageManagerProvider(self.manager)
        builder = MasterFrameBuilder(provider)

        print("Starting making master frames")
        self._build_master_frames(project, builder)
    
        calibrator = Calibrator(project, project.settings.calibration)
        if CALIBRATE_BEFORE_ALIGN:
            provider = CalibratedFrameProvider(provider, calibrator)

        
        print("Starting aligning")
        alignment_pipeline = AlignmentPipeline(provider)
        alignment_pipeline.run(project, project.settings.alignment)

        if not CALIBRATE_BEFORE_ALIGN:
            provider = CalibratedFrameProvider(provider, calibrator)

        stack_provider = provider
        # TODO:現時点ではスタック後ディベイヤーはスタック処理がディベイヤー前非対応なのでできないため直す
        if project.settings.debayer_timing == DebayerTiming.BEFORE_STACK:
            stack_provider = DebayerFrameProvider(stack_provider)

        print("Starting stacking")
        stacking_pipeline = StackingPipeline(stack_provider)
        stacking_pipeline.run(project, project.settings.light_frame)

