from pathlib import Path

import numpy as np
import pytest

from astro_stacker.alignment.transform import ImageTransformer
from astro_stacker.analysis import analyze_motion
from astro_stacker.calibration.bad_pixels import correct_bad_pixels, detect_bad_pixels
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
from astro_stacker.masks import ArrayMaskProvider, compose_masks, generate_star_mask
from astro_stacker.nightscape import composite_nightscape, light_pollution_frame
from astro_stacker.normalization import normalize_image
from astro_stacker.project.settings import StarMaskSettings
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
