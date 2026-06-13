from ..io.image_data import CFAType
import cv2
import numpy as np



PATTERN = {
    CFAType.RGGB: cv2.COLOR_BayerRGGB2RGB,
    CFAType.BGGR: cv2.COLOR_BayerBGGR2RGB,
    CFAType.GBRG: cv2.COLOR_BayerGBRG2RGB,
    CFAType.GRBG: cv2.COLOR_BayerGRBG2RGB,
}


def debayer(image: np.ndarray, cfa_type: CFAType) -> np.ndarray:
    if image.ndim == 3:
        image = image[..., 0]
    
    rgb = cv2.cvtColor(
        image.astype(np.float32),
        PATTERN[cfa_type]
    )

    return rgb.astype(np.float32)