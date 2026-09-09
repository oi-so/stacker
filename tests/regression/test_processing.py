from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

import numpy as np
import pytest
from skimage.transform import SimilarityTransform, warp

from astro_stacker.alignment.transform import ImageTransformer
from astro_stacker.io.image_data import (
    AstroImage,
    AstroImageInfo,
    ColorMode,
    ImageShape,
    TransformData,
)
from astro_stacker.io.image_manager import ImageManager
from astro_stacker.project.settings import StackingMethod, StackingSettings
from astro_stacker.stacking.combiner import ImageCombiner


def frame(path=Path("frame.fit"), color=ColorMode.MONO):
    return AstroImage(AstroImageInfo(path, ImageShape(30, 20, 1), 16, color))


class Provider:
    def __init__(self, arrays):
        self.arrays = arrays
        self.calls = []

    def get_image(self, image):
        index = int(image.info.path.stem)
        self.calls.append(index)
        return self.arrays[index]


@pytest.mark.parametrize("method", list(StackingMethod))
@pytest.mark.parametrize("disk", [False, True])
def test_combinations_match_numpy_and_preserve_inputs(tmp_path, method, disk):
    arrays = np.random.default_rng(17).uniform(1, 300, (7, 20, 30, 3)).astype("float32")
    before = arrays.copy()
    images = [frame(Path(f"{i}.fit")) for i in range(len(arrays))]
    provider = Provider(arrays)
    combiner = ImageCombiner(
        provider, memory_limit=4096 if disk else 1024**2, disk_reserve=0, temp_dir=tmp_path
    )
    settings = StackingSettings(sigma=1.5, iterations=3)
    result = combiner.combine(images, method, settings)
    expected = {
        StackingMethod.AVERAGE: lambda: arrays.mean(axis=0),
        StackingMethod.ADD: lambda: arrays.sum(axis=0),
        StackingMethod.MEDIAN: lambda: np.median(arrays, axis=0),
        StackingMethod.MAXIMUM: lambda: arrays.max(axis=0),
        StackingMethod.MINIMUM: lambda: arrays.min(axis=0),
        StackingMethod.MINMAX_MEAN: lambda: np.sort(arrays, axis=0)[1:-1].mean(axis=0),
    }
    if method == StackingMethod.SIGMA_CLIP:
        data = arrays.copy()
        for _ in range(3):
            mean, std = np.nanmean(data, axis=0), np.nanstd(data, axis=0)
            std[std < 1e-8] = 1
            data[np.abs(data - mean) > 1.5 * std] = np.nan
        expected_result = np.nanmean(data, axis=0)
    else:
        expected_result = expected[method]()
    np.testing.assert_allclose(result, expected_result, rtol=2e-6, atol=1e-4)
    np.testing.assert_array_equal(arrays, before)
    assert result.dtype == np.float32
    assert provider.calls == list(range(7))
    assert not list(tmp_path.iterdir())


def test_stack_cancel_and_load_error_close_disk_mapping(tmp_path):
    images = [frame(Path(f"{i}.fit")) for i in range(3)]
    provider = Provider(np.ones((3, 20, 30, 1), dtype="float32"))
    combiner = ImageCombiner(provider, memory_limit=1, disk_reserve=0, temp_dir=tmp_path)
    assert (
        combiner.combine(
            images, StackingMethod.MEDIAN, is_cancelled=lambda: len(provider.calls) >= 2
        )
        is None
    )
    assert not list(tmp_path.iterdir())

    def fail(image):
        if image is images[1]:
            raise RuntimeError("read failure")
        return np.ones((20, 30, 1), dtype="float32")

    provider.get_image = fail
    with pytest.raises(RuntimeError, match="read failure"):
        combiner.combine(images, StackingMethod.MEDIAN)
    assert not list(tmp_path.iterdir())


def test_disk_budget_and_free_space_preflight(tmp_path, monkeypatch):
    images = [frame(Path("0.fit"))] * 3
    provider = Provider(np.ones((1, 20, 30, 1), dtype="float32"))
    combiner = ImageCombiner(provider, memory_limit=1, disk_limit=1, temp_dir=tmp_path)
    with pytest.raises(ValueError, match="一時領域"):
        combiner.combine(images, StackingMethod.MEDIAN)
    combiner.disk_limit = 1024**2
    from types import SimpleNamespace

    monkeypatch.setattr(
        "astro_stacker.stacking.combiner.shutil.disk_usage", lambda _: SimpleNamespace(free=0)
    )
    with pytest.raises(ValueError, match="一時領域"):
        combiner.combine(images, StackingMethod.MEDIAN)
    assert not list(tmp_path.iterdir())


def test_disabled_frames_shape_and_small_population():
    images = [frame(Path(f"{i}.fit")) for i in range(3)]
    provider = Provider([np.ones((2, 2), dtype="float32")] * 2 + [np.ones((3, 3))])
    images[2].info.enabled = False
    combiner = ImageCombiner(provider)
    np.testing.assert_array_equal(combiner.combine(images), np.ones((2, 2)))
    with pytest.raises(ValueError, match="3枚"):
        combiner.combine(images, StackingMethod.MINMAX_MEAN)
    images[2].info.enabled = True
    with pytest.raises(ValueError, match="same shape"):
        combiner.combine(images)


def test_byte_cache_eviction_invalidation_and_oversized_frame(tmp_path, monkeypatch):
    images = []
    for i in range(3):
        path = tmp_path / str(i)
        path.write_bytes(b"a")
        images.append(frame(path))
    calls = []

    def load(image):
        calls.append(image)
        return np.full((4, 4), len(calls), dtype="float32")

    monkeypatch.setattr("astro_stacker.io.image_manager.load_image", load)
    manager = ImageManager(max_cache_bytes=128)
    manager.get_image(images[0])
    manager.get_image(images[1])
    manager.get_image(images[0])
    manager.get_image(images[2])
    assert len(calls) == 3
    assert manager.is_loaded(images[0]) and not manager.is_loaded(images[1])
    assert manager.cached_bytes == 128
    images[0].info.path.write_bytes(b"changed")
    assert not manager.is_loaded(images[0])
    manager.get_image(images[0])
    assert manager.cached_bytes == 128
    manager.unload_all()
    assert manager.cached_bytes == 0
    manager.max_cache_bytes = 32
    manager.get_image(images[0])
    assert manager.loaded_count() == 0


def test_concurrent_load_is_shared(tmp_path, monkeypatch):
    path = tmp_path / "same.fit"
    path.touch()
    image = frame(path)
    started, release = Event(), Event()
    calls = []

    def load(_):
        calls.append(1)
        started.set()
        assert release.wait(5)
        return np.ones((4, 4), dtype="float32")

    monkeypatch.setattr("astro_stacker.io.image_manager.load_image", load)
    manager = ImageManager()
    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(manager.get_image, image)
        assert started.wait(5)
        second = pool.submit(manager.get_image, frame(path))
        release.set()
        assert first.result() is second.result()
    assert len(calls) == 1


def test_affine_warp_matches_reference_and_preserves_bayer_colours():
    y, x = np.mgrid[:80, :90]
    image = (1000 * np.exp(-((x - 40) ** 2 + (y - 40) ** 2) / 20)).astype("float32")
    transform = SimilarityTransform(rotation=0.013, translation=(2.3, -1.7))
    f = frame()
    f.info.transform = TransformData(matrix=transform.params)
    result = ImageTransformer().apply_transform(image[..., None], f)[..., 0]
    expected = warp(image, inverse_map=transform.inverse, preserve_range=True)
    # OpenCV linear interpolation quantizes fractional coordinates to 1/32 px.
    assert np.max(np.abs(result - expected)) < image.max() * 0.005
    bayer = np.empty((81, 91, 1), dtype="float32")
    f.info.color_mode = ColorMode.BAYER
    for dy in range(2):
        for dx in range(2):
            bayer[dy::2, dx::2, 0] = 1 + dy * 2 + dx
    result = ImageTransformer().apply_transform(bayer, f)
    for dy in range(2):
        for dx in range(2):
            np.testing.assert_allclose(result[10 + dy : 60 : 2, 10 + dx : 60 : 2], 1 + dy * 2 + dx)
    f.info.transform = TransformData(matrix=np.eye(3))
    assert ImageTransformer().apply_transform(bayer, f) is bayer
