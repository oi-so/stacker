"""Composable workflows for aligned export, HDR, and time-lapse material."""

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from ..core.frame_provider import FrameProvider
from ..export.aligned import export_aligned_frames
from ..grouping import make_windows
from ..hdr import group_by_exposure, group_manually, merge_hdr, tone_map
from ..io.image_data import AstroImage
from ..io.saver import save_image
from ..metadata.stacked import stack_metadata
from ..moving_object.capture_time import capture_midpoint
from ..project.settings import HDRSettings, HDRStopAfter, StackingSettings, TimelapseSettings
from ..stacking.combiner import ImageCombiner


@dataclass
class WorkflowResult:
    products: dict[str, np.ndarray] = field(default_factory=dict)
    paths: list[Path] = field(default_factory=list)
    metadata: dict[str, dict] = field(default_factory=dict)


def _save_product(result, name, image, folder, suffix, metadata, bit_depth=None):
    result.products[name] = image
    result.metadata[name] = metadata
    if folder is not None:
        path = folder / f"{name}{suffix}"
        save_image(image, path, metadata=metadata, bit_depth=bit_depth)
        result.paths.append(path)


class HDRPipeline:
    """Stack exposure groups on one caller-supplied aligned coordinate grid."""

    def __init__(self, provider: FrameProvider):
        self.provider = provider

    def run(
        self,
        frames: list[AstroImage],
        stack_settings: StackingSettings,
        hdr_settings: HDRSettings,
        *,
        output_directory: Path | None = None,
        suffix: str = ".fits",
        bit_depth=None,
        progress=None,
        is_cancelled=None,
    ) -> WorkflowResult:
        groups = (
            group_by_exposure(frames, hdr_settings.group_tolerance)
            if hdr_settings.auto_group
            else group_manually(frames, hdr_settings.manual_groups)
        )
        result = WorkflowResult()
        exposure_stacks = []
        exposure_times = []
        for index, group in enumerate(groups, 1):
            if is_cancelled and is_cancelled():
                raise InterruptedError("HDR processing cancelled")
            stack = ImageCombiner(self.provider).combine(
                list(group.frames), stack_settings.method, stack_settings,
                progress=progress, is_cancelled=is_cancelled,
                combine_msg=f"HDR露出グループ {index}/{len(groups)}",
            )
            if stack is None:
                raise InterruptedError("HDR processing cancelled")
            name = f"exposure_{index:03d}_{group.exposure_time:g}s_stack"
            metadata = stack_metadata(group.frames, stack_settings.method)
            _save_product(result, name, stack, output_directory, suffix, metadata, bit_depth)
            exposure_stacks.append(stack)
            exposure_times.append(group.exposure_time)
        if hdr_settings.stop_after == HDRStopAfter.EXPOSURE_STACKS:
            return result
        hdr, validity = merge_hdr(
            exposure_stacks,
            exposure_times,
            black_level=hdr_settings.black_level,
            white_level=hdr_settings.white_level,
            is_cancelled=is_cancelled,
        )
        _save_product(result, "hdr_linear", hdr, output_directory, suffix, {"HDR": True}, bit_depth)
        result.products["hdr_validity_mask"] = validity
        if hdr_settings.stop_after == HDRStopAfter.TONE_MAP:
            mapped = tone_map(hdr, hdr_settings.tone_mapping)
            _save_product(result, "hdr_tonemapped", mapped, output_directory, suffix, {"HDRTMAP": True}, bit_depth)
        return result


class TimelapseStackPipeline:
    def __init__(self, provider: FrameProvider):
        self.provider = provider

    def run(
        self,
        frames: list[AstroImage],
        stack_settings: StackingSettings,
        timelapse_settings: TimelapseSettings,
        output_directory: Path,
        *,
        suffix: str = ".fits",
        bit_depth=None,
        progress=None,
        is_cancelled=None,
    ) -> WorkflowResult:
        groups = make_windows(
            frames,
            timelapse_settings.window_size,
            timelapse_settings.step,
            timelapse_settings.include_partial,
        )
        result = WorkflowResult()
        for index, group in enumerate(groups, 1):
            if is_cancelled and is_cancelled():
                raise InterruptedError("Time-lapse stacking cancelled")
            image = ImageCombiner(self.provider).combine(
                list(group.frames), stack_settings.method, stack_settings,
                progress=progress, is_cancelled=is_cancelled,
                combine_msg=f"タイムラプス {index}/{len(groups)}",
            )
            if image is None:
                raise InterruptedError("Time-lapse stacking cancelled")
            times = [capture_midpoint(frame) for frame in group.frames]
            valid_times = [value for value in times if value is not None]
            metadata = stack_metadata(group.frames, stack_settings.method)
            if valid_times:
                metadata.update({
                    "TSTART": min(valid_times).isoformat(),
                    "TCENTER": valid_times[len(valid_times) // 2].isoformat(),
                    "TEND": max(valid_times).isoformat(),
                })
            _save_product(
                result, f"stack_{index:06d}", image, output_directory, suffix,
                metadata, bit_depth,
            )
        return result


class AlignedExportPipeline:
    def __init__(self, provider: FrameProvider):
        self.provider = provider

    def run(self, frames, output_directory, **kwargs) -> WorkflowResult:
        return WorkflowResult(
            paths=export_aligned_frames(frames, self.provider, output_directory, **kwargs)
        )
