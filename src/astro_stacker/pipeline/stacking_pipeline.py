from ..alignment.transform import AlignedFrameProvider, ImageTransformer
from ..analysis.quality import quality_weights, select_frames
from ..core.frame_provider import FrameProvider
from ..drizzle import DrizzleCombiner
from ..masks.artifacts import inpaint_masked_pixels
from ..masks.weights import (
    AlignedMaskProvider,
    AlignmentValidityMaskProvider,
    CompositeMaskProvider,
    WeightMaskProvider,
)
from ..moving_object.provider import MovingObjectAlignedFrameProvider
from ..moving_object.transform import MovingObjectTransformBuilder
from ..normalization.frame import NormalizedFrameProvider, background_level
from ..project.project import Project
from ..project.settings import StackingSettings
from ..stacking.combiner import ImageCombiner
from ..utils.timer import timer


class StackingPipeline:
    def __init__(
        self,
        provider: FrameProvider,
        source_mask_provider: WeightMaskProvider | None = None,
        aligned_mask_provider: WeightMaskProvider | None = None,
    ):
        self.provider = provider
        self.source_mask_provider = source_mask_provider
        self.aligned_mask_provider = aligned_mask_provider

    def run(
        self,
        project: Project,
        settings: StackingSettings,
        progress=None,
        is_cancelled=None,
        requested_workers: int = 0,
    ) -> None:
        provider = self.provider
        moving_object = project.settings.moving_object
        drizzle = project.settings.processing.drizzle
        if drizzle.enabled and not project.settings.use_alignment:
            raise ValueError("Drizzleには恒星基準の位置合わせが必要です。")
        transform_builder = None
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
            if not drizzle.enabled:
                provider = MovingObjectAlignedFrameProvider(
                    provider,
                    ImageTransformer(),
                    transform_builder,
                )
        elif project.settings.use_alignment and not drizzle.enabled:
            provider = AlignedFrameProvider(provider, ImageTransformer())

        frames = [
            frame for frame in project.light_frames
            if frame.info.enabled and (not project.settings.use_alignment or frame.info.is_aligned)
        ]

        if not frames:
            raise ValueError("No light frames available for stacking")

        frames, rejection_reasons = select_frames(
            frames, project.settings.processing.frame_selection
        )
        project.view_state["frame_rejection_reasons"] = {
            str(path): reason for path, reason in rejection_reasons.items()
        }
        if not frames:
            raise ValueError("Frame selection excluded all light frames")

        target_background = None
        if settings.background_normalization != "none":
            reference_data = provider.get_image(frames[0])
            if settings.exposure_normalization:
                exposure = frames[0].info.exposure_time
                if exposure is None or exposure <= 0:
                    raise ValueError("Exposure normalization requires positive exposure metadata")
                reference_data = reference_data / exposure
            target_background = background_level(
                reference_data, settings.background_normalization
            )
        if settings.exposure_normalization or settings.background_normalization != "none":
            provider = NormalizedFrameProvider(
                provider,
                exposure=settings.exposure_normalization,
                background_method=settings.background_normalization,
                target_background=target_background,
            )

        mask_providers = []
        if (
                settings.use_weight_masks
                and project.settings.use_alignment
                and not drizzle.enabled
        ):
            mask_providers.append(
                AlignmentValidityMaskProvider(
                    transform_for=(
                        transform_builder.transform_for
                        if moving_object.enabled and transform_builder is not None
                        else None
                    )
                )
            )
        if self.source_mask_provider is not None:
            mask_providers.append(
                AlignedMaskProvider(
                    self.source_mask_provider,
                    transform_for=(
                        transform_builder.transform_for
                        if moving_object.enabled and transform_builder is not None
                        else None
                    ),
                )
                if project.settings.use_alignment and not drizzle.enabled
                else self.source_mask_provider
            )
        if self.aligned_mask_provider is not None:
            # This provider already returns masks in the aligned output grid.
            # Applying AlignedMaskProvider here would transform it twice.
            mask_providers.append(self.aligned_mask_provider)
        masks = CompositeMaskProvider(mask_providers) if mask_providers else None
        weights = quality_weights(frames) if settings.use_quality_weights else None

        with timer("StackWorkers", True):
            resources = project.settings.processing.resources
            combiner = (
                DrizzleCombiner(provider)
                if drizzle.enabled
                else ImageCombiner(
                    provider,
                    memory_limit=resources.stack_memory_bytes,
                    disk_limit=resources.stack_disk_bytes,
                    disk_reserve=resources.disk_reserve_bytes,
                    temp_dir=resources.temp_directory,
                )
            )

            if drizzle.enabled:
                result = combiner.combine(
                    frames,
                    scale=drizzle.scale,
                    pixfrac=drizzle.pixfrac,
                    method=settings.method,
                    progress=progress,
                    is_cancelled=is_cancelled,
                    mask_provider=masks,
                    frame_weights=weights,
                    transform_for=(
                        transform_builder.transform_for
                        if moving_object.enabled and transform_builder is not None
                        else None
                    ),
                )
            else:
                result = combiner.combine(
                    frames,
                    settings.method,
                    settings,
                    progress=progress,
                    is_cancelled=is_cancelled,
                    combine_msg="スタック後画像",
                    mask_provider=masks,
                    frame_weights=weights,
                    requested_workers=requested_workers,
                )

            # An artifact mask intentionally contributes no data.  If every
            # aligned frame excludes the same location, ImageCombiner marks it
            # invalid and fills it with zero, which is displayed as a black
            # wire/pole-shaped hole.  Repair only those no-sample pixels using
            # adjacent stacked sky; never modify pixels supported by a frame.
            if (
                result is not None
                and (
                    self.source_mask_provider is not None
                    or self.aligned_mask_provider is not None
                )
                and combiner.last_valid_mask is not None
            ):
                result = inpaint_masked_pixels(result, combiner.last_valid_mask <= 0)

            project.result.stacked_image = result
            from ..metadata.stacked import stack_metadata
            project.result.metadata = stack_metadata(frames, settings.method) if result is not None else {}
            if result is not None and drizzle.enabled:
                project.result.metadata["DRIZZLE"] = drizzle.scale
                project.result.metadata["PIXFRAC"] = drizzle.pixfrac
            if result is not None:
                project.result.validity_mask = combiner.last_valid_mask
            # Reuse the reference WCS only when output pixels use that grid.
            reference = project.reference_image
            if result is not None and project.settings.use_alignment and not moving_object.enabled and reference:
                wcs = reference.info.wcs
                if getattr(wcs, "has_celestial", False):
                    output_wcs = wcs.deepcopy()
                    if drizzle.enabled:
                        output_wcs.wcs.crpix = (
                            (output_wcs.wcs.crpix - 0.5) * drizzle.scale + 0.5
                        )
                        if output_wcs.wcs.has_cd():
                            output_wcs.wcs.cd /= drizzle.scale
                        else:
                            output_wcs.wcs.cdelt /= drizzle.scale
                    project.result.metadata.update(dict(output_wcs.to_header(relax=True)))
            return
