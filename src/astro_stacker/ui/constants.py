from enum import StrEnum


class FrameType(StrEnum):
    LIGHT = "lights"
    DARK = "darks"
    FLAT = "flats"
    FLAT_DARK = "flat_darks"
    BIAS = "biases"

    
    @property
    def display_name(self) -> str:
        return {
            FrameType.LIGHT: "Light Frames",
            FrameType.DARK: "Dark Frames",
            FrameType.FLAT: "Flat Frames",
            FrameType.FLAT_DARK: "Flat Darks",
            FrameType.BIAS: "Bias Frames",
        }[self]