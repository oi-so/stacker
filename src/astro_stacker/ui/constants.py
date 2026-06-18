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
            FrameType.LIGHT: "Lights",
            FrameType.DARK: "Darks",
            FrameType.FLAT: "Flats",
            FrameType.FLAT_DARK: "Flat Darks",
            FrameType.BIAS: "Bias",
        }[self]

    @property
    def ja_name(self) -> str:
        return {
            FrameType.LIGHT: "ライト",
            FrameType.DARK: "ダーク",
            FrameType.FLAT: "フラット",
            FrameType.FLAT_DARK: "フラットダーク",
            FrameType.BIAS: "バイアス",
        }[self]


MASTER_TO_FRAME_TYPE = {
    "master_dark": FrameType.DARK,
    "master_flat": FrameType.FLAT,
    "master_flat_dark": FrameType.FLAT_DARK,
    "master_bias": FrameType.BIAS,
}
