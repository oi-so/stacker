from ..io.image_data import CFAType
import cv2
import numpy as np


PATTERN = {
    CFAType.RGGB: cv2.COLOR_BayerRGGB2RGB,
    CFAType.BGGR: cv2.COLOR_BayerBGGR2RGB,
    CFAType.GBRG: cv2.COLOR_BayerGBRG2RGB,
    CFAType.GRBG: cv2.COLOR_BayerGRBG2RGB,
}


def neutralize_background(rgb: np.ndarray):
    # 各チャンネルの低輝度領域中央値
    bg_r = np.median(rgb[..., 0])
    bg_g = np.median(rgb[..., 1])
    bg_b = np.median(rgb[..., 2])

    mean_bg = (bg_r + bg_g + bg_b) / 3

    rgb[..., 0] *= mean_bg / (bg_r + 1e-8)
    rgb[..., 1] *= mean_bg / (bg_g + 1e-8)
    rgb[..., 2] *= mean_bg / (bg_b + 1e-8)

    return rgb

def debayer(image: np.ndarray, cfa_type: CFAType,
            black_level: float = 0.0,
            out_dtype=np.float32) -> np.ndarray:
    if cfa_type not in PATTERN:
        return image.astype(out_dtype, copy=False)

    img = np.squeeze(image).astype(np.float32)

    # ブラックレベル補正
    img = img - black_level
    img = np.maximum(img, 0)

    white_level = 65535

    img = img / white_level
    img = np.clip(img, 0, 1)

    # OpenCV用変換
    tmp = (img * 65535.0).astype(np.uint16)

    rgb = cv2.cvtColor(tmp, PATTERN[cfa_type])

    # 出力型
    if out_dtype == np.float64:
        return neutralize_background(rgb.astype(np.float64) / 65535.0)
    else:
        return neutralize_background(rgb.astype(out_dtype) / 65535.0)
