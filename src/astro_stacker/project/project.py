from dataclasses import dataclass, field
from pathlib import Path

from ..io.image_data import AstroImage
from ..project.settings import StackingSettings, AlignmentSettings, CalibrationSettings
import numpy as np




@dataclass
class ProjectSettings:
    calibration: CalibrationSettings = field(default_factory=CalibrationSettings)
    alignment: AlignmentSettings = field(default_factory=AlignmentSettings)

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