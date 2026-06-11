from dataclasses import dataclass
from ...io.image_data import AstroImageInfo


@dataclass
class ProjectData:
    lights: list[AstroImageInfo]
    darks: list[AstroImageInfo]
    flats: list[AstroImageInfo]
    biases: list[AstroImageInfo]
    flat_darks: list[AstroImageInfo]