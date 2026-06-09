from dataclasses import dataclass, field
from pathlib import Path

from ..io.image_data import AstroImage
from settings import StackingSettings, AlignmentSettings
import numpy as np




@dataclass
class ProjectSettings:
    light_frame_settings: StackingSettings = field(default_factory=StackingSettings)
    dark_frame_settings: StackingSettings = field(default_factory=StackingSettings)
    flat_frame_settings: StackingSettings = field(default_factory=StackingSettings)
    flat_dark_frame_settings: StackingSettings = field(default_factory=StackingSettings)
    bias_frame_settings: StackingSettings = field(default_factory=StackingSettings)



@dataclass
class ProjectResult:
    stacked_image: np.ndarray | None = None



@dataclass
class Project:
    light_frames: list[AstroImage] = field(default_factory=list)
    dark_frames: list[AstroImage] = field(default_factory=list)
    flat_frames: list[AstroImage] = field(default_factory=list)
    flat_dark_frames: list[AstroImage] = field(default_factory=list)
    bias_frames: list[AstroImage] = field(default_factory=list)

    reference_image: AstroImage | None = None


    output_path: Path | None = None
    project_name: str = "Untitled"
    settings: ProjectSettings = field(default_factory=ProjectSettings)
    result: ProjectResult = field(default_factory=ProjectResult)