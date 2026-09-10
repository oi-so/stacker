import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from ..io.image_data import AstroImage
from ..moving_object.models import MovingObjectSettings
from ..project.settings import (
    AlignmentSettings,
    CalibrationSettings,
    DebayerTiming,
    ProcessingOptions,
    StackingSettings,
)


@dataclass
class ProjectSettings:
    calibration: CalibrationSettings = field(default_factory=CalibrationSettings)
    alignment: AlignmentSettings = field(default_factory=AlignmentSettings)
    use_alignment: bool = True
    moving_object: MovingObjectSettings = field(default_factory=MovingObjectSettings)
    debayer_timing: DebayerTiming = DebayerTiming.BEFORE_STACK

    light_frame: StackingSettings = field(default_factory=StackingSettings)
    dark_frame: StackingSettings = field(default_factory=StackingSettings)
    flat_frame: StackingSettings = field(default_factory=StackingSettings)
    flat_dark_frame: StackingSettings = field(default_factory=StackingSettings)
    bias_frame: StackingSettings = field(default_factory=StackingSettings)
    processing: ProcessingOptions = field(default_factory=ProcessingOptions)


@dataclass
class AppSettings:
    temp_directory: Path | None = None



@dataclass
class ProjectResult:
    stacked_image: np.ndarray | None = None
    validity_mask: np.ndarray | None = None
    metadata: dict = field(default_factory=dict)



@dataclass 
class CalibrationFrames:
    darks: list[AstroImage] = field(default_factory=list)
    flats: list[AstroImage] = field(default_factory=list)
    flat_darks: list[AstroImage] = field(default_factory=list)
    biases: list[AstroImage] = field(default_factory=list)


@dataclass
class MasterCalibrationFrames:
    dark: np.ndarray | None = None
    flat: np.ndarray | None = None
    flat_dark: np.ndarray | None = None
    bias: np.ndarray | None = None

    sub_frame: np.ndarray | None = None


@dataclass(frozen=True)
class AlignmentSignature:
    enabled_paths: frozenset[Path]
    reference_path: Path | None
    sigma: float
    max_stars: int
    calibrate_before_align: bool
    use_wcs: bool = False
    calibration_state: tuple = ()


@dataclass
class AlignmentSession:
    session_id: str
    reference_path: Path | None
    reference_name: str | None
    created_at: datetime


@dataclass
class Project:
    light_frames: list[AstroImage] = field(default_factory=list)
    calibration_frames: CalibrationFrames = field(default_factory=CalibrationFrames)
    master_calibration_frames: MasterCalibrationFrames = field(default_factory=MasterCalibrationFrames)

    reference_image: AstroImage | None = None
    app_settings: AppSettings = field(default_factory=AppSettings)
    USE_CPU_COUNT: int = 0


    output_path: Path | None = None
    project_name: str = "Untitled"
    project_path: Path | None = None
    view_state: dict = field(default_factory=dict)
    notes: str = ""
    settings: ProjectSettings = field(default_factory=ProjectSettings)
    result: ProjectResult = field(default_factory=ProjectResult)
    cache_directory: Path | None = None

    known_paths: set[Path] = field(default_factory=set)
    alignment_signature: AlignmentSignature | None = None
    alignment_sessions: dict[str, AlignmentSession] = field(default_factory=dict)
    current_alignment_session_id: str | None = None

    on_reference_image_changed: Callable[[AstroImage | None], None] | None = field(default=None, repr=False, compare=False)

    def make_alignment_signature(self) -> AlignmentSignature:
        from .codec import fingerprint
        calibration_state = []
        cosmetic = self.settings.processing.cosmetic_correction
        if self.settings.alignment.calibrate_before_align or cosmetic.enabled:
            for name in ("darks", "flats", "flat_darks", "biases"):
                active = getattr(self.settings.calibration, "use_" + name)
                entries = []
                if active:
                    for frame in getattr(self.calibration_frames, name):
                        if frame.info.enabled:
                            try:
                                signature = fingerprint(frame.info.path)
                            except OSError:
                                signature = None
                            entries.append((frame.info.path, signature))
                calibration_state.append((name, active, tuple(entries)))
        if cosmetic.enabled:
            try:
                bad_pixel_signature = (
                    fingerprint(cosmetic.bad_pixel_map_path)
                    if cosmetic.bad_pixel_map_path is not None
                    else None
                )
            except OSError:
                bad_pixel_signature = None
            calibration_state.append(
                (
                    "cosmetic_correction",
                    cosmetic.enabled,
                    cosmetic.bad_pixel_map_path,
                    cosmetic.method,
                    bad_pixel_signature,
                )
            )
        return AlignmentSignature(
            enabled_paths=frozenset(
                frame.info.path
                for frame in self.light_frames
                if frame.info.enabled
            ),
            reference_path=(
                self.reference_image.info.path
                if self.reference_image
                else None
            ),
            sigma=self.settings.alignment.sigma,
            max_stars=self.settings.alignment.max_stars,
            calibrate_before_align=
                self.settings.alignment.calibrate_before_align,
            use_wcs=self.settings.alignment.use_wcs,
            calibration_state=tuple(calibration_state),
        )

    def is_alignment_valid(self) -> bool:
        if (self.alignment_signature != self.make_alignment_signature()):
            return False

        sessions = self.get_alignment_sessions()
        return len(sessions) == 1
    

    def create_alignment_session(self) -> str:
        session_id = str(uuid.uuid4())

        self.alignment_sessions[session_id] = (
            AlignmentSession(
                session_id=session_id,
                reference_path=(
                    self.reference_image.info.path
                    if self.reference_image
                    else None
                ),
                reference_name=(
                    self.reference_image.info.path.name
                    if self.reference_image else None
                ),
                created_at=datetime.now(UTC),
            )
        )

        self.current_alignment_session_id = session_id
        return session_id
    
    def get_alignment_sessions(self, enabled_only: bool = True) -> set[str]:
        frames = (
            [f for f in self.light_frames if f.info.enabled]
            if enabled_only
            else self.light_frames
        )

        return {
            f.info.alignment_session_id
            for f in frames
            if f.info.alignment_session_id is not None
        }


    def set_reference_image(self, image: AstroImage | None):
        if self.reference_image is image:
            return

        self.reference_image = image

        if self.on_reference_image_changed:
            self.on_reference_image_changed(image)
