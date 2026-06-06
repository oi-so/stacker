import tifffile
import numpy as np
from pathlib import Path



def save_tiff(image: np.ndarray, path: Path) -> None:
    arr = image.data

    tifffile.imwrite(path, arr)