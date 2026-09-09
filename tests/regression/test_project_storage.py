import shutil

import numpy as np
import pytest
from astropy.wcs import WCS

from astro_stacker.core.provider import ImageManagerProvider
from astro_stacker.io.history import (
    adopt_alignment_history,
    history_path,
    save_alignment_history,
    save_history,
)
from astro_stacker.io.image_data import TransformData
from astro_stacker.io.image_manager import ImageManager
from astro_stacker.io.loader import load_info
from astro_stacker.io.saver import save_fits
from astro_stacker.moving_object.models import CatalogObject, MovingObjectAnchor
from astro_stacker.platesolve.solver import (
    AstrometryNetSolver,
    PlateSolveResult,
    PlateSolveSettings,
)
from astro_stacker.project.project import Project
from astro_stacker.project.settings import StackingMethod
from astro_stacker.project.storage import load_project, save_project


def make_project(folder):
    folder.mkdir(exist_ok=True)
    project = Project()
    for i in range(3):
        path = folder / f"{i}.fits"
        save_fits(
            np.full((12, 16), i + 1, dtype="float32"),
            path,
            metadata={"EXPTIME": 20, "ISO": 400, "FNUMBER": 2.8},
        )
        project.light_frames.append(load_info(path))
    project.known_paths = {f.info.path for f in project.light_frames}
    project.reference_image = project.light_frames[0]
    session = project.create_alignment_session()
    for i, frame in enumerate(project.light_frames):
        frame.info.transform = TransformData(
            matrix=np.array([[1.0, 0.0, i], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
        )
        frame.info.alignment_session_id = session
    project.alignment_signature = project.make_alignment_signature()
    save_alignment_history(project)
    return project


def attach_solution(frame):
    wcs = WCS(naxis=2)
    wcs.wcs.crpix = [8, 6]
    wcs.wcs.crval = [120, 20]
    wcs.wcs.cdelt = [-1 / 3600, 1 / 3600]
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    frame.info.wcs = wcs
    result = PlateSolveResult(wcs, 120, 20, 1)
    frame._plate_solve_cache = ((ImageManager.cache_key(frame), PlateSolveSettings()), result)
    save_history(frame)


def test_project_roundtrip_and_relocation(tmp_path):
    folder = tmp_path / "original"
    project = make_project(folder)
    project.light_frames[-1].info.enabled = False
    project.alignment_signature = project.make_alignment_signature()
    project.settings.light_frame.method = StackingMethod.MINMAX_MEAN
    project.settings.light_frame.iterations = 4
    project.settings.moving_object.anchors = [
        MovingObjectAnchor(project.light_frames[0].info.path, 120, 20)
    ]
    project.settings.moving_object.catalog_object = CatalogObject("C/2025 A1", "Example comet")
    project.light_frames[1].info.capture_time_override_utc = "2026-09-09T01:00:00Z"
    project.view_state = {
        "selected": project.light_frames[1].info.path,
        "category": "lights",
        "zoom": [2, 0, 0, 2, 0, 0],
    }
    project.notes = "撮影条件のメモ"
    attach_solution(project.light_frames[0])
    from astro_stacker.stars.star_data import Star, StarCatalog

    project.light_frames[1].info.stars.all_stars = StarCatalog([Star(3, 4, 100, 200)])
    save_project(project, folder / "night.astrostacker")
    moved = tmp_path / "moved"
    shutil.copytree(folder, moved)
    restored, warnings = load_project(moved / "night.astrostacker")
    assert not warnings
    assert restored.is_alignment_valid()
    assert restored.light_frames[-1].info.enabled is False
    assert restored.settings.light_frame.method is StackingMethod.MINMAX_MEAN
    assert restored.settings.light_frame.iterations == 4
    assert restored.notes == "撮影条件のメモ"
    assert restored.settings.moving_object.anchors[0].frame_path == moved / "0.fits"
    assert restored.view_state["selected"] == moved / "1.fits"
    assert restored.light_frames[1].info.capture_time_override_utc == "2026-09-09T01:00:00Z"
    np.testing.assert_array_equal(
        restored.light_frames[2].info.transform.matrix,
        project.light_frames[2].info.transform.matrix,
    )
    assert restored.reference_image is restored.light_frames[0]
    assert restored.reference_image.info.wcs.has_celestial
    assert len(restored.alignment_sessions) == 1
    assert restored.light_frames[1].info.stars.all_stars.stars[0].flux == 100


def test_image_history_skips_decoding_and_solver_and_adopts_alignment(tmp_path, monkeypatch):
    project = make_project(tmp_path)
    attach_solution(project.light_frames[0])
    monkeypatch.setattr(
        "astro_stacker.io.loader.load_standard_info", lambda _: pytest.fail("decode")
    )
    for key, (extensions, info, pixels) in list(
        __import__("astro_stacker.io.loader", fromlist=["LOADERS"]).LOADERS.items()
    ):
        monkeypatch.setitem(
            __import__("astro_stacker.io.loader", fromlist=["LOADERS"]).LOADERS,
            key,
            (extensions, lambda _: pytest.fail("metadata decode"), pixels),
        )
    restored = [load_info(f.info.path) for f in project.light_frames]
    monkeypatch.setattr(
        AstrometryNetSolver, "_find_executable", lambda *_: pytest.fail("solver called")
    )
    result = AstrometryNetSolver().solve(restored[0], ImageManagerProvider(ImageManager()))
    assert result.pixel_scale_arcsec == 1
    other = Project(light_frames=restored)
    adopt_alignment_history(other)
    assert other.is_alignment_valid()


def test_missing_or_changed_file_invalidates_all_alignment(tmp_path):
    project = make_project(tmp_path)
    path = tmp_path / "night.astrostacker"
    save_project(project, path)
    project.light_frames[1].info.path.unlink()
    restored, warnings = load_project(path)
    assert warnings and not restored.light_frames[1].info.enabled
    assert all(not f.info.is_aligned for f in restored.light_frames)
    assert not restored.is_alignment_valid()
    # A changed reference must also invalidate standalone transform history.
    save_fits(np.ones((12, 16), dtype="float32") * 99, project.light_frames[0].info.path)
    frame = load_info(project.light_frames[2].info.path)
    assert not frame.info.is_aligned


def test_corrupt_sidecar_falls_back_and_bad_project_fails(tmp_path):
    project = make_project(tmp_path)
    history_path(project.light_frames[0].info.path).write_text("{ broken")
    assert load_info(project.light_frames[0].info.path).info.shape.width == 16
    bad = tmp_path / "bad.astrostacker"
    bad.write_text('{"format":"astro-stacker-project", "version":999}')
    with pytest.raises(ValueError):
        load_project(bad)


def test_atomic_project_failure_keeps_previous_file(tmp_path, monkeypatch):
    project = make_project(tmp_path)
    path = tmp_path / "night.astrostacker"
    save_project(project, path)
    previous = path.read_bytes()

    def fail(*args):
        raise OSError("disk full")

    monkeypatch.setattr("astro_stacker.project.codec.os.replace", fail)
    with pytest.raises(OSError):
        save_project(project, path)
    assert path.read_bytes() == previous
    assert not list(tmp_path.glob("*.tmp"))


def test_save_does_not_bless_stale_loaded_metadata(tmp_path):
    project = make_project(tmp_path)
    frame = project.light_frames[0]
    frame.info.iso = 1234
    save_fits(np.ones((12, 16), dtype="float32"), frame.info.path, metadata={"ISO": 800})
    save_project(project, tmp_path / "changed.astrostacker")
    restored, warnings = load_project(tmp_path / "changed.astrostacker")
    assert warnings
    assert restored.light_frames[0].info.iso == 800
    assert not restored.is_alignment_valid()


def test_calibration_settings_invalidate_reused_alignment(tmp_path):
    project = make_project(tmp_path)
    assert project.is_alignment_valid()
    project.settings.calibration.use_darks = True
    assert not project.is_alignment_valid()


def test_project_cannot_overwrite_source_image(tmp_path):
    project = make_project(tmp_path)
    path = project.light_frames[0].info.path
    before = path.read_bytes()
    with pytest.raises(ValueError, match="上書き"):
        save_project(project, path)
    assert path.read_bytes() == before
