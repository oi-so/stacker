"""Ground transform analysis and optional fixed-ground stack/export."""

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ..alignment.transform import ImageTransformer
from ..core.frame_provider import FrameProvider
from ..export.aligned import export_aligned_frames
from ..ground.alignment import GroundAligner, GroundAlignmentResult
from ..ground.provider import GroundAlignedFrameProvider
from ..io.image_data import AstroImage
from ..masks.weights import ArrayMaskProvider
from ..project.settings import StackingSettings
from ..stacking.combiner import ImageCombiner


@dataclass
class GroundPipelineResult:
    transforms: dict[Path, np.ndarray]
    diagnostics: dict[Path, GroundAlignmentResult]
    stacked_image: np.ndarray | None = None
    exported_paths: list[Path] | None = None


class GroundStackPipeline:
    def __init__(self, provider: FrameProvider):
        self.provider = provider

    def run(
        self,
        frames: list[AstroImage],
        settings: StackingSettings,
        *,
        reference: AstroImage | None = None,
        ground_mask: np.ndarray | None = None,
        detector: str = "orb",
        model: str = "similarity",
        stack: bool = True,
        export_directory: Path | None = None,
        suffix: str = ".fits",
        progress=None,
        is_cancelled=None,
    ) -> GroundPipelineResult:
        enabled = [frame for frame in frames if frame.info.enabled]
        if not enabled:
            raise ValueError("No ground frames")
        reference = reference or enabled[len(enabled) // 2]
        reference_data = self.provider.get_image(reference)
        transforms = {reference.info.path: np.eye(3, dtype=np.float64)}
        diagnostics = {
            reference.info.path: GroundAlignmentResult(np.eye(3), 0, 0, 0.0)
        }
        aligner = GroundAligner(detector, model)
        for index, frame in enumerate(enabled, 1):
            if is_cancelled and is_cancelled():
                raise InterruptedError("Ground alignment cancelled")
            if frame.info.path != reference.info.path:
                measured = aligner.align(
                    self.provider.get_image(frame), reference_data, ground_mask
                )
                transforms[frame.info.path] = measured.matrix
                diagnostics[frame.info.path] = measured
            if progress:
                progress("地上固定位置合わせ", index, len(enabled), frame.info.path.name)
        provider = GroundAlignedFrameProvider(self.provider, transforms)
        result = GroundPipelineResult(transforms, diagnostics)
        if export_directory is not None:
            transformer = ImageTransformer()
            footprint = ArrayMaskProvider(
                lambda frame: transformer.apply_mask(
                    np.ones(reference_data.shape[:2], dtype=np.float32),
                    transforms[frame.info.path],
                )
            )
            result.exported_paths = export_aligned_frames(
                enabled,
                provider,
                export_directory,
                suffix=suffix,
                mask_provider=footprint,
                include_alignment_footprint=False,
                progress=progress,
                is_cancelled=is_cancelled,
            )
        if stack:
            result.stacked_image = ImageCombiner(provider).combine(
                enabled,
                settings.method,
                settings,
                progress=progress,
                is_cancelled=is_cancelled,
                combine_msg="地上固定スタック",
            )
        return result
