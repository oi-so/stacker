import tifffile
import numpy as np
from pathlib import Path



def save_tiff(image: np.ndarray, path: Path) -> None:
    tifffile.imwrite(path, image)


def save_preview_tiff(image: np.ndarray, path: Path):
    img = image.astype(np.float32).copy()

    img -= img.min()

    if img.max() > 0:
        img /= img.max()

    img = (img * 65535).astype(np.uint16)

    tifffile.imwrite(path, img)