from dataclasses import dataclass, field
from pathlib import Path
import numpy as np
from datetime import datetime
import uuid

from ..io.image_data import AstroImage
from ..project.settings import StackingSettings, AlignmentSettings, CalibrationSettings, DebayerTiming


@dataclass
class ProjectSettings:
    calibration: CalibrationSettings = field(default_factory=CalibrationSettings)
    alignment: AlignmentSettings = field(default_factory=AlignmentSettings)
    debayer_timing: DebayerTiming = DebayerTiming.BEFORE_STACK

    light_frame: StackingSettings = field(default_factory=StackingSettings)
    dark_frame: StackingSettings = field(default_factory=StackingSettings)
    flat_frame: StackingSettings = field(default_factory=StackingSettings)
    flat_dark_frame: StackingSettings = field(default_factory=StackingSettings)
    bias_frame: StackingSettings = field(default_factory=StackingSettings)



@dataclass
class ProjectResult:
    stacked_image: np.ndarray | None = None



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


    output_path: Path | None = None
    project_name: str = "Untitled"
    settings: ProjectSettings = field(default_factory=ProjectSettings)
    result: ProjectResult = field(default_factory=ProjectResult)
    cache_directory: Path | None = None

    known_paths: set[Path] = field(default_factory=set)
    alignment_signature: AlignmentSignature | None = None
    alignment_sessions: dict[str, AlignmentSession] = field(default_factory=dict)
    current_alignment_session_id: str | None = None

    def make_alignment_signature(self) -> AlignmentSignature:
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
        )

    def is_alignment_valid(self) -> bool:
        return (
            self.alignment_signature
            == self.make_alignment_signature()
        )
    

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
                created_at=datetime.now(),
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
