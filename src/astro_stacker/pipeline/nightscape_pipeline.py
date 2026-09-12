"""Material-first nightscape workflow built from shared providers and masks."""

from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from ..analysis.motion import GroupSuggestion, analyze_motion, suggest_time_groups
from ..core.frame_provider import FrameProvider
from ..io.image_data import AstroImage
from ..io.saver import save_image
from ..masks.weights import (
    AlignedMaskProvider,
    AlignmentValidityMaskProvider,
    ArrayMaskProvider,
    CompositeMaskProvider,
)
from ..nightscape.composite import composite_nightscape, light_pollution_frame
from ..project.settings import (
    BoundaryMode,
    NightscapeOutput,
    NightscapeSettings,
    ResourceSettings,
    StackingSettings,
)
from ..stacking.combiner import ImageCombiner


@dataclass
class NightscapeResult:
    products: dict[str, np.ndarray] = field(default_factory=dict)
    paths: list[Path] = field(default_factory=list)
    group_suggestion: GroupSuggestion | None = None


def _merge_group_stacks(stacks, masks):
    numerator = np.zeros_like(stacks[0], dtype=np.float64)
    denominator = np.zeros(stacks[0].shape[:2], dtype=np.float64)
    for image, mask in zip(stacks, masks, strict=True):
        weight = mask[..., None] if image.ndim == 3 else mask
        numerator += image * weight
        denominator += mask
    output = np.zeros_like(stacks[0], dtype=np.float32)
    weights = denominator[..., None] if output.ndim == 3 else denominator
    np.divide(numerator, weights, out=output, where=weights > 0)
    return output, (denominator > 0).astype(np.float32)


class NightscapePipeline:
    def __init__(self, sky_provider: FrameProvider, ground_provider: FrameProvider | None = None):
        self.sky_provider = sky_provider
        self.ground_provider = ground_provider or sky_provider

    def run(
        self,
        sky_frames: list[AstroImage],
        ground_frames: list[AstroImage],
        stack_settings: StackingSettings,
        settings: NightscapeSettings,
        sky_mask: np.ndarray,
        *,
        star_mask: np.ndarray | None = None,
        output_directory: Path | None = None,
        suffix: str = ".fits",
        progress=None,
        is_cancelled=None,
        resource_settings: ResourceSettings | None = None,
    ) -> NightscapeResult:
        if not sky_frames or not ground_frames:
            raise ValueError("Nightscape requires sky and ground frames")
        shape = (sky_frames[0].info.shape.height, sky_frames[0].info.shape.width)
        mask = np.asarray(sky_mask, dtype=np.float32)
        if mask.shape != shape:
            raise ValueError("Nightscape mask does not match sky frame dimensions")
        result = NightscapeResult()
        resource_settings = resource_settings or ResourceSettings()
        if settings.output == NightscapeOutput.MASK_ONLY:
            result.products["ground_mask"] = mask
            if star_mask is not None:
                result.products["star_mask"] = star_mask
            if output_directory is not None:
                for name, product in result.products.items():
                    path = output_directory / f"{name}{suffix}"
                    save_image(product, path, frame_type=name)
                    result.paths.append(path)
            return result
        split_index = settings.split_index
        if settings.split_mode == "auto":
            motion = analyze_motion(sky_frames)
            result.group_suggestion = suggest_time_groups(motion, len(sky_frames))
            split_index = (
                result.group_suggestion.split_indices[0]
                if result.group_suggestion.split_indices
                else 0
            )
        groups = [sky_frames]
        if 0 < split_index < len(sky_frames):
            groups = [sky_frames[:split_index], sky_frames[split_index:]]

        base_mask = ArrayMaskProvider(lambda _: mask)
        if settings.star_alignment:
            mask_provider = CompositeMaskProvider(
                [AlignedMaskProvider(base_mask), AlignmentValidityMaskProvider()]
            )
        else:
            mask_provider = base_mask
        sky_stacks = []
        sky_validity = []
        for index, group in enumerate(groups, 1):
            combiner = ImageCombiner(
                self.sky_provider,
                memory_limit=resource_settings.stack_memory_bytes,
                disk_limit=resource_settings.stack_disk_bytes,
                disk_reserve=resource_settings.disk_reserve_bytes,
                temp_dir=resource_settings.temp_directory,
            )
            stack = combiner.combine(
                group,
                stack_settings.method,
                stack_settings,
                progress=progress,
                is_cancelled=is_cancelled,
                combine_msg=f"新星景 星空Group {index}",
                mask_provider=mask_provider,
            )
            if stack is None:
                raise InterruptedError("Nightscape sky stacking cancelled")
            sky_stacks.append(stack)
            sky_validity.append(combiner.last_valid_mask)
            result.products[f"sky_stack_{chr(64 + index)}"] = stack
        sky, sky_validity_mask = _merge_group_stacks(sky_stacks, sky_validity)
        result.products["merged_sky"] = sky

        # Ground material is intentionally never aligned.  Both fixed-camera
        # and tracking workflows use a fixed ground sequence; aligning it here
        # bends buildings and contradicts the material selection made by user.
        ground_settings = settings.ground_stack
        ground = ImageCombiner(
            self.ground_provider,
            memory_limit=resource_settings.stack_memory_bytes,
            disk_limit=resource_settings.stack_disk_bytes,
            disk_reserve=resource_settings.disk_reserve_bytes,
            temp_dir=resource_settings.temp_directory,
        ).combine(
            ground_frames,
            ground_settings.method,
            ground_settings,
            progress=progress,
            is_cancelled=is_cancelled,
            combine_msg="新星景 地上Stack",
        )
        if ground is None:
            raise InterruptedError("Nightscape ground stacking cancelled")
        if ground.shape != sky.shape:
            raise ValueError("Sky and ground materials must have identical dimensions")
        result.products["ground_image" if settings.ground_use_single_frame else "ground_stack"] = ground
        result.products["ground_mask"] = mask
        if star_mask is not None:
            result.products["star_mask"] = star_mask
        pollution = None
        composite_mask = mask * sky_validity_mask
        if settings.smooth_boundary and settings.boundary_smoothing == "gaussian":
            composite_mask = cv2.GaussianBlur(
                composite_mask,
                (0, 0),
                max(0.1, float(settings.transition_width)),
                borderType=cv2.BORDER_REFLECT,
            )
        if settings.boundary_mode == BoundaryMode.LIGHT_POLLUTION:
            pollution = light_pollution_frame(ground, star_mask, blur_scale=settings.blur_scale)
            result.products["light_pollution_frame"] = pollution
        if settings.output == NightscapeOutput.FINAL:
            final, protected = composite_nightscape(
                sky,
                ground,
                composite_mask,
                star_mask=star_mask if settings.use_star_mask else None,
                pollution_frame=pollution,
                background_strength=settings.background_strength,
            )
            result.products["final_composite"] = final
            result.products["protected_ground_mask"] = protected

        legacy_allowed = {
            NightscapeOutput.SKY_ONLY: {"merged_sky"},
            NightscapeOutput.GROUND_ONLY: {"ground_image", "ground_stack"},
            NightscapeOutput.MASK_ONLY: {"ground_mask", "star_mask"},
            NightscapeOutput.MATERIALS: set(result.products),
            NightscapeOutput.FINAL: set(result.products),
        }[settings.output]
        # A checked product list is the current UI's explicit export contract.
        # Retain the old output enum for projects written by older releases.
        allowed = settings.enabled_outputs or legacy_allowed
        if output_directory is not None:
            for name, product in result.products.items():
                if name not in allowed:
                    continue
                path = output_directory / f"{name}{suffix}"
                save_image(product, path, frame_type=name)
                result.paths.append(path)
        return result
