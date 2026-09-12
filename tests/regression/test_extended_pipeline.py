import warnings
from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits

from astro_stacker.alignment.transform import ImageTransformer
from astro_stacker.analysis import analyze_motion, suggest_time_groups
from astro_stacker.calibration.bad_pixels import (
    correct_bad_pixels,
    detect_bad_pixels,
    detect_bad_pixels_from_lights,
)
from astro_stacker.core.provider import PreviewProvider, PreviewSettings
from astro_stacker.drizzle import DrizzleCombiner
from astro_stacker.grouping import make_windows
from astro_stacker.hdr import group_by_exposure, merge_hdr, tone_map
from astro_stacker.io.image_data import (
    AstroImage,
    AstroImageInfo,
    CFAType,
    ColorMode,
    ImageShape,
    TransformData,
)
from astro_stacker.masks import (
    ArrayMaskProvider,
    compose_masks,
    detect_line_candidates,
    generate_star_mask,
    inpaint_masked_pixels,
    polygon_weight_mask,
    polyline_weight_mask,
)
from astro_stacker.nightscape import composite_nightscape, light_pollution_frame
from astro_stacker.normalization import normalize_image
from astro_stacker.obstacles import ObstacleDetector, TrackedObstacleMaskProvider, transform_mask
from astro_stacker.pipeline.extended_pipeline import TimelapseStackPipeline
from astro_stacker.pipeline.nightscape_pipeline import NightscapePipeline
from astro_stacker.pipeline.stacking_pipeline import StackingPipeline
from astro_stacker.project.project import Project
from astro_stacker.project.settings import (
    NightscapeSettings,
    StackingMethod,
    StackingSettings,
    StarMaskSettings,
    TimelapseSettings,
)
from astro_stacker.stacking.combiner import ImageCombiner
from astro_stacker.stars.star_data import Star, StarCatalog


def frame(index: int, exposure: float = 1.0) -> AstroImage:
    info = AstroImageInfo(
        Path(f"{index}.fits"), ImageShape(5, 4, 1), 16, ColorMode.MONO,
        exposure_time=exposure, iso=800, f_number=2.8,
    )
    return AstroImage(info)


class Provider:
    def __init__(self, arrays):
        self.arrays = arrays

    def get_image(self, image):
        return self.arrays[int(image.info.path.stem)]


class CountingPreviewManager:
    def __init__(self, array):
        self.array = array
        self.loads = 0

    def cache_key(self, image):
        return (str(image.info.path), 1)

    def get_image(self, image):
        self.loads += 1
        return self.array


def test_weighted_average_mask_and_zero_sum_are_safe():
    frames = [frame(0), frame(1)]
    arrays = np.stack([np.ones((4, 5)), np.full((4, 5), 3)], dtype=np.float32)
    first = np.ones((4, 5), dtype=np.float32)
    second = np.ones((4, 5), dtype=np.float32)
    first[:, :2] = 0
    second[:, 3:] = 0
    first[:, 2] = second[:, 2] = 0
    masks = ArrayMaskProvider({frames[0].info.path: first, frames[1].info.path: second})
    combiner = ImageCombiner(Provider(arrays))
    result = combiner.combine(frames, mask_provider=masks)
    np.testing.assert_array_equal(result[:, :2], 3)
    np.testing.assert_array_equal(result[:, 2], 0)
    np.testing.assert_array_equal(result[:, 3:], 1)
    np.testing.assert_array_equal(combiner.last_valid_mask[:, 2], 0)


def test_all_one_mask_matches_legacy_average():
    frames = [frame(0), frame(1)]
    arrays = np.random.default_rng(4).random((2, 4, 5), dtype=np.float32)
    plain = ImageCombiner(Provider(arrays)).combine(frames)
    masked = ImageCombiner(Provider(arrays)).combine(
        frames, mask_provider=ArrayMaskProvider(lambda _: np.ones((4, 5)))
    )
    np.testing.assert_allclose(masked, plain)


def test_parallel_prefetch_preserves_order_and_nan_validity():
    frames = [frame(0), frame(1), frame(2)]
    arrays = np.stack(
        [
            np.full((4, 5), 1, dtype=np.float32),
            np.full((4, 5), 3, dtype=np.float32),
            np.full((4, 5), 5, dtype=np.float32),
        ]
    )
    arrays[1, 2, 3] = np.nan
    sequential = ImageCombiner(Provider(arrays)).combine(frames, requested_workers=1)
    parallel_combiner = ImageCombiner(Provider(arrays))
    parallel = parallel_combiner.combine(frames, requested_workers=2)

    np.testing.assert_allclose(parallel, sequential)
    assert parallel[2, 3] == pytest.approx(3)
    assert parallel_combiner.last_valid_mask[2, 3] == 1


def test_preview_is_bounded_and_reused_without_reloading():
    image = AstroImage(
        AstroImageInfo(
            Path("preview.fits"), ImageShape(600, 400, 1), 16, ColorMode.MONO
        )
    )
    manager = CountingPreviewManager(np.ones((400, 600), dtype=np.float32))
    provider = PreviewProvider(manager, max_cache_bytes=16 * 1024**2)
    settings = PreviewSettings(binning=1, debayer=False, max_dimension=256)

    first = provider.get_image(image, settings)
    second = provider.get_image(image, settings)

    assert first.image.shape == (133, 200)
    assert second.image is first.image
    assert manager.loads == 1


def test_mask_composition_and_affine_transform_match_image_grid():
    combined = compose_masks([np.full((5, 5), 0.5), np.full((5, 5), 0.4)])
    np.testing.assert_allclose(combined, 0.2)
    impulse = np.zeros((5, 5), dtype=np.float32)
    impulse[2, 2] = 1
    matrix = np.array([[1, 0, 1], [0, 1, 0], [0, 0, 1]], dtype=float)
    moved = ImageTransformer().apply_mask(impulse, matrix)
    assert moved[2, 3] == pytest.approx(1)
    perspective = np.array(
        [[1, 0, 0], [0, 1, 0], [0.01, 0.005, 1]], dtype=float
    )
    transformed_mask = ImageTransformer().apply_mask(np.ones((5, 5)), perspective)
    transformed_image = ImageTransformer()._warp(np.ones((5, 5)), perspective)
    np.testing.assert_allclose(transformed_mask, transformed_image)


def test_star_mask_uses_fwhm_flux_and_feather():
    catalog = StarCatalog([Star(10, 10, flux=1000, peak=100, fwhm=3, ellipticity=0.3)])
    mask = generate_star_mask((21, 21), catalog, StarMaskSettings(feather=1.5))
    assert mask.dtype == np.float32
    assert mask[10, 10] > mask[0, 0]
    assert np.any((mask > 0) & (mask < 1))


def test_exposure_and_background_normalization():
    image = np.arange(20, dtype=np.float32).reshape(4, 5) + 10
    result = normalize_image(image, exposure_time=2, target_background=20)
    assert np.median(result) == pytest.approx(20)


def test_hdr_grouping_merge_and_tone_mapping():
    frames = [frame(0, 1), frame(1, 1), frame(2, 4)]
    groups = group_by_exposure(frames)
    assert [len(group.frames) for group in groups] == [2, 1]
    radiance = np.full((4, 5), 10, dtype=np.float32)
    short = radiance * 1
    long = radiance * 4
    long[0, 0] = 1000
    hdr, valid = merge_hdr(
        [short, long], [1, 4], black_level=0, white_level=50
    )
    assert hdr[2, 2] == pytest.approx(10, rel=0.05)
    assert hdr[0, 0] == pytest.approx(10, rel=0.05)
    assert np.all(valid == 1)
    mapped = tone_map(hdr)
    assert mapped.min() >= 0 and mapped.max() <= 1
    rgb = np.stack([hdr, hdr * 0.5, hdr * 0.25], axis=-1)
    local = tone_map(rgb, "local", local_scale=2, detail_strength=1.2)
    assert local.shape == rgb.shape
    assert np.isfinite(local).all()


def test_timelapse_windows_keep_or_drop_partial():
    frames = [frame(i) for i in range(103)]
    assert [len(group.frames) for group in make_windows(frames, 10)][-1] == 3
    assert len(make_windows(frames, 10, include_partial=False)) == 10
    sliding = make_windows(frames[:20], 10, step=5)
    assert [(group.frames[0].info.path.stem, len(group.frames)) for group in sliding] == [
        ("0", 10), ("5", 10), ("10", 10), ("15", 5)
    ]


def test_bad_pixel_detection_and_cfa_safe_correction():
    image = np.full((10, 10), 10, dtype=np.float32)
    image[4, 4] = 1000
    bpm = detect_bad_pixels(image, detect_columns=False)
    assert bpm[4, 4] == 1
    corrected = correct_bad_pixels(image, bpm, cfa_type=CFAType.RGGB)
    assert corrected[4, 4] == pytest.approx(10)
    corrected_channel = correct_bad_pixels(image[..., None], bpm[..., None])
    assert corrected_channel[4, 4, 0] == pytest.approx(10)


def test_bad_pixel_detection_rejects_nonfinite_calibration_data():
    image = np.ones((5, 5), dtype=np.float32)
    image[2, 2] = np.nan
    with pytest.raises(ValueError, match="NaN"):
        detect_bad_pixels(image)


def test_bad_pixel_detection_from_lights_keeps_persistent_isolated_pixels():
    frames = [frame(index) for index in range(5)]
    arrays = np.stack(
        [np.full((12, 12), 10 + index * 0.1, dtype=np.float32) for index in range(5)]
    )
    arrays[:, 6, 7] = 1000
    arrays[:, 2:4, 2:4] = 500  # Extended scene/star-like structure is rejected.

    result = detect_bad_pixels_from_lights(
        Provider(arrays), frames, sigma=5, persistence=0.6
    )

    assert result[6, 7] == 1
    assert not np.any(result[2:4, 2:4])


def test_polyline_mask_has_zero_core_feather_and_untouched_background():
    mask = polyline_weight_mask(
        (31, 31),
        [[(4, 15), (26, 15)]],
        line_width=3,
        feather=4,
    )
    assert mask.dtype == np.float32
    assert mask[15, 15] == 0
    assert 0 < mask[19, 15] < 1
    assert mask[0, 0] == 1


def test_polygon_mask_removes_area_without_connecting_separate_lines():
    mask = polygon_weight_mask(
        (30, 30), [[(5, 5), (20, 5), (20, 20), (5, 20)]], feather=0
    )
    assert mask[10, 10] == 0
    assert mask[2, 2] == 1


def test_inpaint_masked_pixels_repairs_only_the_no_sample_hole():
    image = np.full((9, 9), 7.0, dtype=np.float32)
    image[3:6, :] = 0.0
    missing = np.zeros((9, 9), dtype=bool)
    missing[3:6, :] = True

    repaired = inpaint_masked_pixels(image, missing)

    np.testing.assert_allclose(repaired[:3], 7.0)
    np.testing.assert_allclose(repaired[6:], 7.0)
    assert np.all(repaired[3:6] > 0)


def test_tracked_obstacle_mask_uses_nearest_neighbour_for_full_transform():
    source = np.zeros((9, 9), dtype=bool)
    source[2, 2] = True
    transform = TransformData(
        matrix=np.array([[0.0, -1.0, 8.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])
    )
    tracked = transform_mask(source, transform)

    assert tracked.dtype == bool
    assert tracked.sum() == 1
    assert tracked[2, 6]

    item = frame(0)
    item.info.transform = transform
    weights = TrackedObstacleMaskProvider(source).get_mask(item, source.shape)
    assert weights[2, 6] == 0
    assert weights[2, 2] == 1


def test_obstacle_detector_reports_large_single_frame_change_not_stars():
    base = np.zeros((32, 32), dtype=np.float32)
    base[4, 4] = 20  # a point-like star must not become an obstacle candidate
    changed = base.copy()
    changed[14:24, 2:28] = 50

    candidates = ObstacleDetector(confidence_threshold=0.6, minimum_area=32).detect(
        changed, aligned_images=[base, base, base]
    )

    assert len(candidates) == 1
    assert candidates[0].source.value == "auto"
    assert candidates[0].mask[18, 14]
    assert not candidates[0].mask[4, 4]


@pytest.mark.parametrize(
    "opencv_shape",
    [np.array([[1, 2, 20, 21]], dtype=np.int32), np.array([[[1, 2, 20, 21]]], dtype=np.int32)],
)
def test_line_detection_accepts_opencv_result_shapes(monkeypatch, opencv_shape):
    monkeypatch.setattr("cv2.HoughLinesP", lambda *args, **kwargs: opencv_shape)
    candidates = detect_line_candidates(np.zeros((64, 64), dtype=np.float32))
    assert candidates == [[(1.0, 2.0), (20.0, 21.0)]]


def test_artifact_mask_is_applied_during_stacking():
    frames = [frame(0), frame(1)]
    arrays = np.stack(
        [np.full((4, 5), 2, dtype=np.float32), np.full((4, 5), 10, dtype=np.float32)]
    )
    masks = {
        frames[0].info.path: np.ones((4, 5), dtype=np.float32),
        frames[1].info.path: np.ones((4, 5), dtype=np.float32),
    }
    masks[frames[1].info.path][2, 3] = 0
    project = Project(light_frames=frames)
    project.settings.use_alignment = False

    StackingPipeline(Provider(arrays), ArrayMaskProvider(masks)).run(
        project, project.settings.light_frame
    )

    assert project.result.stacked_image[0, 0] == pytest.approx(6)
    assert project.result.stacked_image[2, 3] == pytest.approx(2)


def test_drizzle_reconstructs_larger_grid_and_respects_source_mask():
    frames = [frame(0), frame(1)]
    arrays = np.stack(
        [np.full((4, 5), 2, dtype=np.float32), np.full((4, 5), 6, dtype=np.float32)]
    )
    source_masks = {
        frames[0].info.path: np.ones((4, 5), dtype=np.float32),
        frames[1].info.path: np.ones((4, 5), dtype=np.float32),
    }
    source_masks[frames[1].info.path][1, 2] = 0
    combiner = DrizzleCombiner(Provider(arrays), chunk_rows=3)

    result = combiner.combine(
        frames,
        scale=2,
        pixfrac=1,
        mask_provider=ArrayMaskProvider(source_masks),
    )

    assert result.shape == (8, 10)
    assert result[2, 4] == pytest.approx(2)
    assert result[0, 0] == pytest.approx(4)
    assert np.all(combiner.last_valid_mask == 1)


def test_drizzle_requires_supported_method_and_alignment_scale():
    frames = [frame(0)]
    combiner = DrizzleCombiner(Provider(np.ones((1, 4, 5), dtype=np.float32)))
    with pytest.raises(ValueError, match="Average and Add"):
        combiner.combine(frames, method=StackingMethod.MEDIAN)
    with pytest.raises(ValueError, match="scale"):
        combiner.combine(frames, scale=4)


def test_drizzle_accepts_moving_object_transform_callback():
    frames = [frame(0)]
    arrays = np.ones((1, 4, 5), dtype=np.float32)

    def shifted(_):
        return TransformData(
            matrix=np.array([[1, 0, 1], [0, 1, 0], [0, 0, 1]], dtype=float)
        )

    result = DrizzleCombiner(Provider(arrays)).combine(
        frames, scale=2, pixfrac=1, transform_for=shifted
    )

    assert np.all(result[:, :2] == 0)
    assert np.any(result[:, 2:] > 0)


def test_motion_analysis_reports_reversal_candidate():
    frames = [frame(i) for i in range(5)]
    for item, x in zip(frames, (0, 1, 2, 1, 0), strict=True):
        item.info.transform = TransformData(
            matrix=np.array([[1, 0, x], [0, 1, 0], [0, 0, 1]], dtype=float)
        )
    result = analyze_motion(frames)
    assert result.star_motion
    assert result.reversal_candidates == (3,)
    assert result.recommendation == "star_alignment"
    suggestion = suggest_time_groups(result, len(frames))
    assert suggestion.groups == ((0, 3), (3, 5))


def test_nightscape_composite_preserves_stars_at_boundary():
    sky = np.full((20, 20), 10, dtype=np.float32)
    ground = np.full((20, 20), 2, dtype=np.float32)
    weight = np.zeros((20, 20), dtype=np.float32)
    weight[:10] = 1
    weight[10] = 0.25
    stars = np.zeros((20, 20), dtype=np.float32)
    stars[9:12, 9:12] = 1
    result, protected = composite_nightscape(sky, ground, weight, star_mask=stars)
    assert protected[10, 10] == 1
    assert result[10, 10] == 10
    pollution = light_pollution_frame(sky, stars, blur_scale=2)
    assert pollution.shape == sky.shape


def test_nightscape_composite_accepts_singleton_channel_materials():
    sky = np.full((6, 7, 1), 10, dtype=np.float32)
    ground = np.full((6, 7), 2, dtype=np.float32)
    weight = np.ones((6, 7), dtype=np.float32)
    pollution = np.zeros((6, 7, 1), dtype=np.float32)

    result, _ = composite_nightscape(
        sky,
        ground,
        weight,
        pollution_frame=pollution,
        background_strength=0.25,
    )

    assert result.shape == (6, 7)
    np.testing.assert_allclose(result, 10)


def test_sigma_clip_all_invalid_pixels_does_not_warn():
    frames = [frame(0), frame(1)]
    arrays = np.full((2, 4, 5), np.nan, dtype=np.float32)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = ImageCombiner(Provider(arrays)).combine(
            frames,
            StackingMethod.SIGMA_CLIP,
            StackingSettings(method=StackingMethod.SIGMA_CLIP),
        )
    assert not caught
    assert result is not None
    assert np.all(result == 0)


def test_statistical_stack_removes_custom_temp_file(tmp_path):
    frames = [frame(0), frame(1), frame(2)]
    arrays = np.stack(
        [np.full((4, 5), index, dtype=np.float32) for index in range(3)]
    )
    result = ImageCombiner(
        Provider(arrays),
        memory_limit=1,
        disk_limit=1024**3,
        disk_reserve=0,
        temp_dir=tmp_path,
    ).combine(
        frames,
        StackingMethod.MEDIAN,
        StackingSettings(method=StackingMethod.MEDIAN),
    )
    assert result is not None
    assert not list(tmp_path.glob("astro-stacker-stack-*.dat"))


def test_nightscape_pipeline_can_finish_composite():
    frames = [frame(0), frame(1)]
    arrays = np.stack(
        [np.full((4, 5), 4, dtype=np.float32), np.full((4, 5), 6, dtype=np.float32)]
    )
    settings = NightscapeSettings(star_alignment=False)
    sky_mask = np.ones((4, 5), dtype=np.float32)
    sky_mask[2:] = 0
    result = NightscapePipeline(Provider(arrays)).run(
        frames,
        frames,
        StackingSettings(),
        settings,
        sky_mask,
    )
    assert {"merged_sky", "ground_stack", "ground_mask", "final_composite"} <= set(
        result.products
    )
    np.testing.assert_allclose(result.products["final_composite"][:2], 5)


def test_parallel_timelapse_is_bounded_and_keeps_output_order(tmp_path, monkeypatch):
    frames = [frame(index) for index in range(6)]
    arrays = np.stack(
        [np.full((4, 5), index, dtype=np.float32) for index in range(6)]
    )
    monkeypatch.setattr(
        "astro_stacker.pipeline.extended_pipeline.bounded_workers", lambda *args, **kwargs: 2
    )
    result = TimelapseStackPipeline(Provider(arrays)).run(
        frames,
        StackingSettings(),
        TimelapseSettings(window_size=2, step=2),
        tmp_path,
        requested_workers=2,
    )
    assert [path.name for path in result.paths] == [
        "stack_000001.fits",
        "stack_000002.fits",
        "stack_000003.fits",
    ]
    values = [float(np.mean(fits.getdata(path))) for path in result.paths]
    np.testing.assert_allclose(values, [0.5, 2.5, 4.5])
