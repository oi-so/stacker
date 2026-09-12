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
from astro_stacker.project.settings import (
    AlignmentStrategy,
    BoundaryMode,
    GroundSource,
    NightscapeCaptureMode,
    NightscapeOutput,
    ObstacleMode,
    StackingMethod,
)
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
    bad_pixel_map = folder / "bad-pixels.fits"
    artifact_mask = folder / "wire-mask.fits"
    save_fits(np.zeros((12, 16), dtype="float32"), bad_pixel_map)
    save_fits(np.ones((12, 16), dtype="float32"), artifact_mask)
    project.settings.processing.cosmetic_correction.enabled = True
    project.settings.processing.cosmetic_correction.bad_pixel_map_path = bad_pixel_map
    project.settings.processing.artifact_masks.enabled = True
    project.settings.processing.artifact_masks.mode = ObstacleMode.TRACKED
    project.settings.processing.artifact_masks.reference_mask_path = artifact_mask
    project.settings.processing.artifact_masks.reference_frame_path = project.light_frames[0].info.path
    project.settings.processing.artifact_masks.auto_detect_new = True
    project.settings.processing.artifact_masks.confidence_threshold = 0.75
    project.settings.processing.artifact_masks.mask_paths[
        project.light_frames[0].info.path
    ] = artifact_mask
    project.settings.processing.drizzle.enabled = True
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
    assert restored.settings.processing.cosmetic_correction.enabled
    assert (
        restored.settings.processing.cosmetic_correction.bad_pixel_map_path
        == moved / "bad-pixels.fits"
    )
    assert restored.settings.processing.artifact_masks.mask_paths[
        moved / "0.fits"
    ] == moved / "wire-mask.fits"
    assert restored.settings.processing.artifact_masks.mode is ObstacleMode.TRACKED
    assert restored.settings.processing.artifact_masks.reference_mask_path == moved / "wire-mask.fits"
    assert restored.settings.processing.artifact_masks.reference_frame_path == moved / "0.fits"
    assert restored.settings.processing.artifact_masks.auto_detect_new
    assert restored.settings.processing.artifact_masks.confidence_threshold == 0.75
    assert restored.settings.processing.drizzle.enabled
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


def test_light_only_cosmetic_settings_roundtrip(tmp_path):
    project = make_project(tmp_path)
    cosmetic = project.settings.processing.cosmetic_correction
    cosmetic.enabled = True
    cosmetic.source = "lights"
    cosmetic.light_sigma = 12.0
    cosmetic.light_persistence = 0.8
    project.alignment_signature = project.make_alignment_signature()
    path = tmp_path / "lights-cosmetic.astrostacker"

    save_project(project, path)
    restored, warnings = load_project(path)

    assert not warnings
    restored_cosmetic = restored.settings.processing.cosmetic_correction
    assert restored_cosmetic.source == "lights"
    assert restored_cosmetic.light_sigma == 12.0
    assert restored_cosmetic.light_persistence == 0.8
    assert restored.is_alignment_valid()


def test_nightscape_settings_roundtrip(tmp_path):
    project = make_project(tmp_path)
    nightscape = project.settings.processing.nightscape
    nightscape.output = NightscapeOutput.FINAL
    nightscape.boundary_mode = BoundaryMode.LIGHT_POLLUTION
    nightscape.ground_source = GroundSource.SEPARATE_FRAMES
    nightscape.capture_mode = NightscapeCaptureMode.TRACKING
    nightscape.ground_frame_paths = [project.light_frames[0].info.path]
    nightscape.ground_mask_path = tmp_path / "ground-mask.fits"
    nightscape.ground_use_single_frame = True
    nightscape.ground_stack.method = StackingMethod.SIGMA_CLIP
    nightscape.ground_stack.sigma = 2.5
    nightscape.enabled_outputs = {"merged_sky", "ground_image", "ground_mask"}
    nightscape.star_alignment = True
    nightscape.ground_alignment = False
    nightscape.use_star_mask = False
    nightscape.split_mode = "manual"
    nightscape.split_index = 2
    nightscape.feather = 6.0
    nightscape.blur_scale = 48.0
    nightscape.transition_width = 20.0
    nightscape.background_strength = 0.4
    nightscape.smooth_boundary = False
    nightscape.boundary_smoothing = "feather"
    resources = project.settings.processing.resources
    resources.temp_directory = tmp_path / "stack-temp"
    resources.image_cache_bytes = 512 * 1024**2
    resources.stack_memory_bytes = 768 * 1024**2
    resources.stack_disk_bytes = 32 * 1024**3
    resources.disk_reserve_bytes = 2 * 1024**3

    path = tmp_path / "nightscape.astrostacker"
    save_project(project, path)
    restored, warnings = load_project(path)

    assert not warnings
    restored_nightscape = restored.settings.processing.nightscape
    assert restored_nightscape.capture_mode is NightscapeCaptureMode.TRACKING
    assert restored_nightscape.ground_source is GroundSource.SEPARATE_FRAMES
    assert restored_nightscape.boundary_mode is BoundaryMode.LIGHT_POLLUTION
    assert restored_nightscape.ground_frame_paths == [tmp_path / "0.fits"]
    assert restored_nightscape.ground_mask_path == tmp_path / "ground-mask.fits"
    assert restored_nightscape.ground_stack.method is StackingMethod.SIGMA_CLIP
    assert restored_nightscape.ground_stack.sigma == 2.5
    assert restored_nightscape.enabled_outputs == {
        "merged_sky",
        "ground_image",
        "ground_mask",
    }
    assert restored_nightscape.use_star_mask is False
    assert restored_nightscape.split_mode == "manual"
    assert restored_nightscape.split_index == 2
    assert restored_nightscape.background_strength == 0.4
    assert restored_nightscape.smooth_boundary is False
    assert restored_nightscape.boundary_smoothing == "feather"
    restored_resources = restored.settings.processing.resources
    assert restored_resources.temp_directory == tmp_path / "stack-temp"
    assert restored_resources.image_cache_bytes == 512 * 1024**2
    assert restored_resources.stack_memory_bytes == 768 * 1024**2
    assert restored_resources.stack_disk_bytes == 32 * 1024**3
    assert restored_resources.disk_reserve_bytes == 2 * 1024**3


def test_timelapse_string_alignment_is_accepted(tmp_path):
    project = make_project(tmp_path)
    project.settings.processing.timelapse.alignment = "star_global"
    path = tmp_path / "timelapse-string.astrostacker"

    save_project(project, path)
    restored, warnings = load_project(path)

    assert not warnings
    alignment = restored.settings.processing.timelapse.alignment
    assert getattr(alignment, "value", alignment) == AlignmentStrategy.STAR_GLOBAL.value


def test_project_cannot_overwrite_source_image(tmp_path):
    project = make_project(tmp_path)
    path = project.light_frames[0].info.path
    before = path.read_bytes()
    with pytest.raises(ValueError, match="上書き"):
        save_project(project, path)
    assert path.read_bytes() == before
