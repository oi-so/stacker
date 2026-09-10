"""Top-level processing pipeline orchestration."""

import logging
from pathlib import Path

import numpy as np

from ..calibration.bad_pixels import BadPixelCorrectedFrameProvider
from ..calibration.calibration import Calibrator, MasterFrameBuilder
from ..core.provider import CalibratedFrameProvider, DebayerFrameProvider, ImageManagerProvider
from ..io.image_data import AstroImage
from ..io.image_manager import ImageManager
from ..io.loader import load_info
from ..io.saver import save_fits
from ..masks.weights import FileMaskProvider
from ..pipeline.alignment_pipeline import AlignmentPipeline
from ..pipeline.stacking_pipeline import StackingPipeline
from ..project.project import Project
from ..project.settings import DebayerTiming, StackingMethod

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
        method: StackingMethod,
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

        settings = getattr(project.settings, f"{master_type.removeprefix('master_')}_frame", None)
        master = builder.build(inputs, method, settings, progress, is_cancelled, master_type)
        if master is None:
            return None
        master = master.astype(np.float32, copy=False)
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
            metadata=project.result.metadata,
            frame_type="stacked_light",
        )
        project.output_path = path
        logger.info("Auto-saved stacked result: %s", path)

    def _prepare_alignment_provider(self, project, progress=None, is_cancelled=None):
        calibration = project.settings.calibration
        provider = ImageManagerProvider(self.manager)
        self._build_master_frames(
            project, MasterFrameBuilder(provider), progress, is_cancelled
        )
        calibrator = Calibrator(project, calibration)
        calibrate_before_align = getattr(
            project.settings.alignment,
            "calibrate_before_align",
            CALIBRATE_BEFORE_ALIGN,
        )
        cosmetic = project.settings.processing.cosmetic_correction
        if calibrate_before_align or cosmetic.enabled:
            provider = CalibratedFrameProvider(provider, calibrator)
        if cosmetic.enabled:
            if cosmetic.bad_pixel_map_path is None:
                raise ValueError("Bad Pixel補正が有効ですが、Bad Pixel Mapが未指定です。")
            if not cosmetic.bad_pixel_map_path.exists():
                raise ValueError(f"Bad Pixel Mapが見つかりません: {cosmetic.bad_pixel_map_path}")
            bad_pixel_frame = load_info(cosmetic.bad_pixel_map_path)
            bad_pixel_map = self.manager.get_image(bad_pixel_frame)
            provider = BadPixelCorrectedFrameProvider(
                provider,
                bad_pixel_map,
                method=cosmetic.method,
            )
        return provider, calibrator, calibrate_before_align, cosmetic

    def run_alignment(self, project: Project, progress=None, is_cancelled=None) -> None:
        provider, _, _, _ = self._prepare_alignment_provider(
            project, progress, is_cancelled
        )
        AlignmentPipeline(provider).run(
            project,
            project.settings.alignment,
            progress=progress,
            is_cancelled=is_cancelled,
            requested_workers=project.settings.processing.parallel_workers,
        )

    def run(self, project: Project, progress=None, is_cancelled=None, skip_alignment = False) -> None:
        project.light_frames = [
            frame for frame in project.light_frames
            if (frame.info.exif or {}).get("FRAMTYP") != "stacked_light"
        ]
        if not project.light_frames:
            raise ValueError("No light frames")
        
        if progress:
            progress("マスター生成", 0, 1, "キャリブレーションフレームを作成中...")

        # The project owns calibration choices; adding files enables their
        # category in the controller, but a saved unchecked choice stays off.
        provider, calibrator, calibrate_before_align, cosmetic = (
            self._prepare_alignment_provider(project, progress, is_cancelled)
        )

        if not skip_alignment and not project.is_alignment_valid():
            logger.info("Starting alignment")
            alignment_pipeline = AlignmentPipeline(provider)
            alignment_pipeline.run(
                project,
                project.settings.alignment,
                progress=progress,
                is_cancelled=is_cancelled,
                requested_workers=project.settings.processing.parallel_workers,
            )
        else:
            if skip_alignment:
                logger.info("Skipping alignment")
            else:
                logger.info("Using existing alignment")

        if is_cancelled and is_cancelled():
            return

        if not calibrate_before_align and not cosmetic.enabled:
            provider = CalibratedFrameProvider(provider, calibrator)

        if progress:
            progress("スタック", 0, 1, "準備中")
        stack_provider = provider
        if (
            project.settings.debayer_timing == DebayerTiming.BEFORE_STACK
            or project.settings.processing.drizzle.enabled
        ):
            stack_provider = DebayerFrameProvider(stack_provider)

        source_masks = None
        artifact_settings = project.settings.processing.artifact_masks
        if artifact_settings.enabled:
            if not artifact_settings.mask_paths:
                raise ValueError("電線・障害物除去が有効ですが、マスクが登録されていません。")

            def load_mask(path: Path) -> np.ndarray:
                return self.manager.get_image(load_info(path))

            source_masks = FileMaskProvider(artifact_settings.mask_paths, load_mask)

        logger.info("Starting stacking")
        stacking_pipeline = StackingPipeline(stack_provider, source_masks)
        stacking_pipeline.run(
            project,
            project.settings.light_frame,
            progress=progress,
            is_cancelled=is_cancelled,
            requested_workers=project.settings.processing.parallel_workers,
        )

        if progress:
            progress("自動保存中", 0, 1, "stacked.fits")
        self._auto_save_stacked(project)
