from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from astropy.io import fits
from astropy.wcs import WCS

from astro_stacker.alignment.detection import process_frame
from astro_stacker.core.resources import alignment_workers
from astro_stacker.io.image_data import AstroImage, AstroImageInfo, ColorMode, ImageShape
from astro_stacker.platesolve.solver import AstrometryNetSolver, PlateSolveSettings
from astro_stacker.stars.detector import background_stats, detect_stars


def make_frame():
    return AstroImage(
        AstroImageInfo(Path("synthetic.fit"), ImageShape(100, 50, 1), 16, ColorMode.MONO)
    )


class Provider:
    def __init__(self):
        self.version = 1
        self.loads = 0

    def cache_token(self, frame):
        return self.version

    def get_image(self, frame):
        self.loads += 1
        return np.ones((50, 100, 1), dtype="float32")


def test_plate_solve_cache_invalidates_and_keeps_original_pixel_wcs(monkeypatch):
    commands = []

    class Process:
        returncode = 0

        def __init__(self, command, **kwargs):
            commands.append(command)
            wcs = WCS(naxis=2)
            wcs.wcs.crpix = [50, 25]
            wcs.wcs.cdelt = [-1 / 3600, 1 / 3600]
            wcs.wcs.crval = [120, 20]
            wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
            fits.PrimaryHDU(header=wcs.to_header()).writeto(command[command.index("--wcs") + 1])
            Path(command[command.index("--solved") + 1]).touch()

        def poll(self):
            return 0

    monkeypatch.setattr("astro_stacker.platesolve.solver.subprocess.Popen", Process)
    monkeypatch.setattr(AstrometryNetSolver, "_find_executable", lambda *args: "solve-field")
    solver, frame, provider = AstrometryNetSolver(), make_frame(), Provider()
    result = solver.solve(frame, provider)
    assert result.pixel_scale_arcsec == pytest.approx(1)
    result.wcs.wcs.crval = [0, 0]
    cached = solver.solve(frame, provider)
    assert cached.wcs.wcs.crval[0] == 120
    assert len(commands) == provider.loads == 1
    provider.version += 1
    solver.solve(frame, provider)
    solver.solve(frame, provider, PlateSolveSettings(downsample=4))
    assert len(commands) == provider.loads == 3
    provider.version += 1
    provider.get_image = lambda _: np.ones((20, 7000), dtype="float32")
    solver.solve(frame, provider)
    assert commands[-1][commands[-1].index("--downsample") + 1] == "4"
    solver.solve(frame, provider, PlateSolveSettings(auto_downsample=False))
    assert commands[-1][commands[-1].index("--downsample") + 1] == "2"
    for command in commands:
        for flag in ["--new-fits", "--match", "--rdls", "--corr"]:
            assert command[command.index(flag) + 1] == "none"
    with pytest.raises(RuntimeError, match="キャンセル"):
        solver.solve(frame, provider, is_cancelled=lambda: True)


def test_plate_solve_mono_does_not_mutate_input():
    a = np.array([[np.nan, 2.0]], dtype="float32")
    result = AstrometryNetSolver._as_mono(a)
    assert np.isnan(a[0, 0])
    assert np.isfinite(result).all()
    b = np.ones((5, 5), dtype="float32")
    assert AstrometryNetSolver._as_mono(b) is b


def test_star_centroids_remain_at_original_resolution():
    rng = np.random.default_rng(42)
    image = rng.normal(100, 2, (1024, 1024)).astype("float32")
    y, x = np.mgrid[-8:9, -8:9]
    centers = [(101, 133), (503, 509), (801, 833)]
    for cx, cy in centers:
        image[cy - 8 : cy + 9, cx - 8 : cx + 9] += 500 * np.exp(-(x * x + y * y) / 8)
    stars = detect_stars(image).brightest(3).stars
    assert len(stars) == 3
    for cx, cy in centers:
        assert min(np.hypot(star.x - cx, star.y - cy) for star in stars) < 0.1
    _, median, noise = background_stats(image)
    assert median == pytest.approx(100, abs=0.1)
    assert noise == pytest.approx(2, abs=0.1)


def test_detection_reuses_only_matching_input_and_settings(monkeypatch):
    provider, frame = Provider(), make_frame()
    from astro_stacker.stars.star_data import StarCatalog

    calls = []

    def detect(*args, **kwargs):
        calls.append(1)
        return StarCatalog([])

    monkeypatch.setattr("astro_stacker.alignment.detection.detect_stars", detect)
    first = process_frame(provider, frame, 5, 500)
    assert process_frame(provider, frame, 5, 500) is first
    provider.version += 1
    process_frame(provider, frame, 5, 500)
    process_frame(provider, frame, 6, 500)
    assert len(calls) == provider.loads == 3


@pytest.mark.parametrize(
    "cpus,available,expected", [(1, 8 * 1024**3, 1), (8, 8 * 1024**3, 2), (4, 128 * 1024**2, 1)]
)
def test_worker_budget(monkeypatch, cpus, available, expected):
    monkeypatch.setattr("astro_stacker.core.resources.os.cpu_count", lambda: cpus)
    monkeypatch.setattr(
        "astro_stacker.core.resources.psutil.virtual_memory",
        lambda: SimpleNamespace(available=available),
    )
    assert alignment_workers(100 * 1024**2) == expected
