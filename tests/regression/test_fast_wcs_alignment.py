from pathlib import Path

import numpy as np

from astro_stacker.io.image_data import AstroImage, AstroImageInfo, ColorMode, ImageShape
from astro_stacker.pipeline.alignment_pipeline import AlignmentPipeline
from astro_stacker.project.project import Project
from astro_stacker.project.settings import AlignmentSettings, ReferenceMode


class LinearWCS:
    has_celestial = True

    def __init__(self, offset_x=0.0, offset_y=0.0):
        self.offset_x = offset_x
        self.offset_y = offset_y

    def pixel_to_world_values(self, x, y):
        return np.asarray(x) + self.offset_x, np.asarray(y) + self.offset_y

    def world_to_pixel_values(self, ra, dec):
        return np.asarray(ra) - self.offset_x, np.asarray(dec) - self.offset_y


def make_frame(name: str, wcs) -> AstroImage:
    frame = AstroImage(
        AstroImageInfo(Path(name), ImageShape(100, 80, 1), 16, ColorMode.MONO)
    )
    frame.info.wcs = wcs
    return frame


def test_alignment_can_use_existing_wcs_without_loading_pixels():
    reference = make_frame("reference.fits", LinearWCS())
    shifted = make_frame("shifted.fits", LinearWCS(5, -3))
    project = Project(light_frames=[reference, shifted], reference_image=reference)
    settings = AlignmentSettings(reference_mode=ReferenceMode.MANUAL, use_wcs=True)

    AlignmentPipeline(provider=object()).run(project, settings)

    np.testing.assert_allclose(
        shifted.info.transform.matrix,
        np.array([[1, 0, 5], [0, 1, -3], [0, 0, 1]], dtype=float),
        atol=1e-7,
    )
    assert shifted.info.alignment_data.rms_error < 1e-7
    assert project.is_alignment_valid()
