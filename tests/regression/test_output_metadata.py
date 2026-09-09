from pathlib import Path

import numpy as np
import pytest
import tifffile
from astropy.io import fits
from PIL import Image

from astro_stacker.io.image_data import (
    AstroImage,
    AstroImageInfo,
    ColorMode,
    ImageShape,
    TransformData,
)
from astro_stacker.io.saver import save_image
from astro_stacker.metadata.stacked import stack_metadata
from astro_stacker.pipeline.processing_pipeline import ProcessingPipeline
from astro_stacker.pipeline.stacking_pipeline import StackingPipeline
from astro_stacker.project.project import Project


def make_frame(i, exposure, iso, fnumber):
    return AstroImage(
        AstroImageInfo(
            Path(f"{i}.fits"),
            ImageShape(12, 10, 1),
            16,
            ColorMode.MONO,
            exposure_time=exposure,
            iso=iso,
            f_number=fnumber,
        )
    )


def test_metadata_uses_actual_frames_and_freezes_at_stack_time():
    frames = [
        make_frame(0, 30, 400, 2.8),
        make_frame(1, 60, 800, 4),
        make_frame(2, 60, 800, 4),
        make_frame(3, 999, 3200, 8),
        make_frame(4, 999, 6400, 16),
    ]
    for frame in frames[:4]:
        frame.info.transform = TransformData(matrix=np.eye(3))
    frames[3].info.enabled = False
    project = Project(light_frames=frames)

    class Provider:
        def get_image(self, image):
            assert image in frames[:3]
            return np.ones((10, 12, 1), dtype="float32")

    StackingPipeline(Provider()).run(project, project.settings.light_frame)
    result = project.result.metadata
    assert result["EXPTIME"] == 150
    assert result["ISO"] == 800 and result["FNUMBER"] == 4
    assert result["NSTACK"] == 3
    assert "30 x 1" in result["COMMENT"] and "60 x 2" in result["COMMENT"]
    assert "400 x 1" in result["COMMENT"] and "800 x 2" in result["COMMENT"]
    frames[0].info.exposure_time = 999
    frames[1].info.enabled = False
    assert project.result.metadata["EXPTIME"] == 150


@pytest.mark.parametrize(
    "suffix,bit_depth",
    [("fits", 32), ("tif", 16), ("tif", 32), ("jpg", 8), ("png", 8), ("png", 16)],
)
def test_output_metadata_roundtrip_and_precision(tmp_path, suffix, bit_depth):
    arrays = np.arange(10 * 12 * 3, dtype="float32").reshape(10, 12, 3) + 0.25
    metadata = stack_metadata(
        [make_frame(0, 30, 400, 2.8), make_frame(1, 60, 800, 4), make_frame(2, 60, 800, 4)],
        "average",
    )
    metadata["COMMENT"] += "\n観測メモ"
    path = tmp_path / ("stacked." + suffix)
    save_image(arrays, path, metadata=metadata, bit_depth=bit_depth)
    if suffix == "fits":
        h = fits.getheader(path)
        assert isinstance(h["EXPTIME"], (float, int))
        assert h["EXPTIME"] == 150 and h["ISO"] == 800 and h["FNUMBER"] == 4
        assert "60 x 2" in str(h["COMMENT"])
        np.testing.assert_array_equal(np.moveaxis(fits.getdata(path), 0, -1), arrays)
    elif suffix == "tif":
        with tifffile.TiffFile(path) as t:
            exif = t.pages[0].tags[34665].value
            assert exif["ExposureTime"] == (150, 1)
            assert exif["ISOSpeedRatings"] == 800
            assert exif["FNumber"] == (4, 1)
            assert "観測メモ" in exif["UserComment"]
            pixels = t.asarray()
            assert pixels.shape == arrays.shape
            from astro_stacker.io.loader import load_image, load_info

            frame = load_info(path)
            assert frame.info.exposure_time == 150 and frame.info.iso == 800
            if bit_depth == 32:
                np.testing.assert_array_equal(load_image(frame), arrays)
            if bit_depth == 32:
                np.testing.assert_array_equal(pixels, arrays)
                assert pixels.dtype == np.float32
            else:
                assert pixels.dtype == np.uint16
    else:
        with Image.open(path) as image:
            exif = image.getexif().get_ifd(34665)
            assert float(exif[33434]) == 150 and exif[34855] == 800 and float(exif[33437]) == 4
            assert "観測メモ" in exif[37510][8:].decode("utf-16")
        from astro_stacker.io.loader import load_info

        loaded_info = load_info(path).info
        assert (
            loaded_info.exposure_time == 150
            and loaded_info.iso == 800
            and loaded_info.f_number == 4
        )
        if suffix == "png" and bit_depth == 16:
            import cv2

            assert cv2.imread(str(path), cv2.IMREAD_UNCHANGED).dtype == np.uint16


def test_missing_values_and_ties():
    result = stack_metadata(
        [make_frame(0, None, None, 0), make_frame(1, 10, 800, 4), make_frame(2, 20, 400, 2.8)],
        "median",
    )
    assert result["EXPTIME"] == 30 and result["ISO"] == 800 and result["FNUMBER"] == 4
    assert "unknown x 1" in result["COMMENT"]
    missing = stack_metadata([make_frame(0, None, None, None)], "average")
    assert "EXPTIME" not in missing and "ISO" not in missing and "FNUMBER" not in missing


def test_auto_save_uses_result_snapshot(tmp_path):
    frame = make_frame(0, 999, 100, 1.4)
    frame.info.path = tmp_path / "source.fits"
    project = Project(light_frames=[frame])
    project.result.stacked_image = np.ones((10, 12, 1), dtype="float32")
    project.result.metadata = {"EXPTIME": 150.0, "ISO": 800, "FNUMBER": 4.0}
    ProcessingPipeline(None)._auto_save_stacked(project)
    assert fits.getheader(project.output_path)["EXPTIME"] == 150
