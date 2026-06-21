"""Top-level processing pipeline orchestration."""

from pathlib import Path
import logging

import numpy as np

from ..io.image_data import AstroImage
from ..io.image_manager import ImageManager
from ..io.loader import load_info
from ..io.saver import save_fits
from ..core.provider import ImageManagerProvider, DebayerFrameProvider, CalibratedFrameProvider
from ..project.project import Project
from ..project.settings import DebayerTiming
from ..calibration.calibration import MasterFrameBuilder, Calibrator
from ..pipeline.alignment_pipeline import AlignmentPipeline
from ..pipeline.stacking_pipeline import StackingPipeline

logger = logging.getLogger(__name__)

# Project setting can override this through AlignmentSettings.calibrate_before_align.
CALIBRATE_BEFORE_ALIGN: bool = True


class ProcessingPipeline:
    def __init__(self, manager: ImageManager):
        self.manager = manager

    @staticmethod
    def _unique_path(folder: Path, stem: str, suffix: str) -> Path:
        candidate = folder / f"{stem}{suffix}"
        index = 2
        while candidate.exists():
            candidate = folder / f"{stem}{index}{suffix}"
            index += 1
        return candidate

    @staticmethod
    def _enabled_regular(frames: list[AstroImage]) -> list[AstroImage]:
        return [frame for frame in frames if frame.info.enabled and not frame.info.is_master]

    @staticmethod
    def _enabled_master(frames: list[AstroImage], master_type: str) -> AstroImage | None:
        for frame in frames:
            if frame.info.enabled and frame.info.is_master and frame.info.master_type == master_type:
                return frame
        return None

    def _save_master(
        self,
        project: Project,
        frames: list[AstroImage],
        array: np.ndarray,
        master_type: str,
    ) -> AstroImage | None:
        if not frames:
            return None

        folder = frames[0].info.path.parent
        path = self._unique_path(folder, master_type, ".fits")
        metadata = frames[0].info.exif or {}
        save_fits(array, path, metadata=metadata, frame_type=master_type)
        master = load_info(path)
        master.info.enabled = True
        master.info.is_master = True
        master.info.master_type = master_type
        frames.append(master)
        project.known_paths.add(path)
        logger.info("Created %s: %s", master_type, path)
        return master

    def _build_or_load_master(
        self,
        project: Project,
        builder: MasterFrameBuilder,
        frames: list[AstroImage],
        use_frame: bool,
        method: str,
        master_type: str,
        progress=None,
        is_cancelled=None,
    ) -> np.ndarray | None:
        if not use_frame:
            return None

        existing = self._enabled_master(frames, master_type)
        if existing is not None:
            logger.info("Using existing %s: %s", master_type, existing.info.path)
            return self.manager.get_image(existing).astype(np.float32, copy=True)

        inputs = self._enabled_regular(frames)
        if not inputs:
            return None

        master = builder.build(inputs, method, progress, is_cancelled, master_type).astype(np.float32, copy=False)
        for frame in inputs:
            frame.info.enabled = False
        self._save_master(project, frames, master, master_type)
        return master

    def _build_master_frames(self, project: Project, builder: MasterFrameBuilder, progress = None, is_cancelled = None) -> None:
        settings = project.settings.calibration
        settings.use_biases = settings.use_biases and bool(project.calibration_frames.biases)
        settings.use_darks = settings.use_darks and bool(project.calibration_frames.darks)
        settings.use_flats = settings.use_flats and bool(project.calibration_frames.flats)
        settings.use_flat_darks = settings.use_flat_darks and bool(project.calibration_frames.flat_darks)

        logger.info("Building calibration masters")
        bias = self._build_or_load_master(
            project,
            builder,
            project.calibration_frames.biases,
            settings.use_biases,
            project.settings.bias_frame.method,
            "master_bias",
            progress,
            is_cancelled,
        )
        dark = self._build_or_load_master(
            project,
            builder,
            project.calibration_frames.darks,
            settings.use_darks,
            project.settings.dark_frame.method,
            "master_dark",
            progress,
            is_cancelled,
        )
        flat_dark = self._build_or_load_master(
            project,
            builder,
            project.calibration_frames.flat_darks,
            settings.use_flat_darks,
            project.settings.flat_dark_frame.method,
            "master_flat_dark",
            progress,
            is_cancelled,
        )
        flat = self._build_or_load_master(
            project,
            builder,
            project.calibration_frames.flats,
            settings.use_flats,
            project.settings.flat_frame.method,
            "master_flat",
            progress,
            is_cancelled,
        )

        if bias is not None:
            if dark is not None:
                dark = np.clip(dark - bias, 0, None).astype(np.float32, copy=False)
            if flat_dark is not None:
                flat_dark = np.clip(flat_dark - bias, 0, None).astype(np.float32, copy=False)

        if flat is not None:
            if flat_dark is not None:
                flat = flat - flat_dark
            if bias is not None:
                flat = flat - bias
            mean = float(np.mean(flat))
            if not np.isfinite(mean) or abs(mean) < 1e-8:
                logger.warning("Master flat mean is zero; flat calibration will be skipped")
                flat = None
            else:
                flat = np.clip(flat / mean, 1e-8, None).astype(np.float32, copy=False)

        project.master_calibration_frames.bias = bias
        project.master_calibration_frames.dark = dark
        project.master_calibration_frames.flat_dark = flat_dark
        project.master_calibration_frames.flat = flat

        sub_frames = [frame for frame in (dark, bias) if frame is not None]
        project.master_calibration_frames.sub_frame = (
            np.sum(sub_frames, axis=0).astype(np.float32, copy=False) if sub_frames else None
        )

    def _auto_save_stacked(self, project: Project) -> None:
        if project.result.stacked_image is None or not project.light_frames:
            return
        folder = project.light_frames[0].info.path.parent
        path = self._unique_path(folder, "stacked", ".fits")
        save_fits(
            project.result.stacked_image,
            path,
            metadata=project.light_frames[0].info.exif,
            frame_type="stacked_light",
        )
        project.output_path = path
        logger.info("Auto-saved stacked result: %s", path)

    def run(self, project: Project, progress=None, is_cancelled=None) -> None:
        project.light_frames = [
            frame for frame in project.light_frames
            if (frame.info.exif or {}).get("FRAMTYP") != "stacked_light"
        ]
        if not project.light_frames:
            raise ValueError("No light frames")
        
        if progress:
            progress("マスター生成", 0, 1, "キャリブレーションフレームを作成中...")

        # Preserve manual settings when called from UI, but auto-enable frame
        # types in CLI/test use when the user has not opened settings.
        calibration = project.settings.calibration
        calibration.use_biases = calibration.use_biases or bool(project.calibration_frames.biases)
        calibration.use_darks = calibration.use_darks or bool(project.calibration_frames.darks)
        calibration.use_flats = calibration.use_flats or bool(project.calibration_frames.flats)
        calibration.use_flat_darks = calibration.use_flat_darks or bool(project.calibration_frames.flat_darks)

        provider = ImageManagerProvider(self.manager)
        builder = MasterFrameBuilder(provider)

        self._build_master_frames(project, builder, progress, is_cancelled)

        calibrator = Calibrator(project, calibration)
        calibrate_before_align = getattr(
            project.settings.alignment,
            "calibrate_before_align",
            CALIBRATE_BEFORE_ALIGN,
        )
        if calibrate_before_align:
            provider = CalibratedFrameProvider(provider, calibrator)

        logger.info("Starting alignment")
        alignment_pipeline = AlignmentPipeline(provider)
        alignment_pipeline.run(project, project.settings.alignment, progress=progress, is_cancelled=is_cancelled)
        if is_cancelled and is_cancelled(): return

        if not calibrate_before_align:
            provider = CalibratedFrameProvider(provider, calibrator)

        if progress:
            progress("スタック", 0, 1, "準備中")
        stack_provider = provider
        if project.settings.debayer_timing == DebayerTiming.BEFORE_STACK:
            stack_provider = DebayerFrameProvider(stack_provider)

        logger.info("Starting stacking")
        stacking_pipeline = StackingPipeline(stack_provider)
        stacking_pipeline.run(project, project.settings.light_frame, progress=progress, is_cancelled=is_cancelled)

        if progress:
            progress("自動保存中", 0, 1, "stacked.fits")
        self._auto_save_stacked(project)