from dataclasses import dataclass, field
from pathlib import Path

from ..io.image_data import AstroImage



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