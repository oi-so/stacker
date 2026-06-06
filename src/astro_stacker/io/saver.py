import tifffile
import numpy as np
from pathlib import Path



def save_tiff(image: np.ndarray, path: Path) -> None:
    tifffile.imwrite(path, image)


def save_preview_tiff(image, path):
    img = image.copy()

    img -= img.min()
    img /= img.max()

    img = (img * 65535).astype(np.uint16)

    tifffile.imwrite(path, img)