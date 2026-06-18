#!/usr/bin/env python3
"""Print min/max/mean/dtype statistics for image frames."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import numpy as np

from astro_stacker.io.loader import load_image, load_info


def iter_paths(paths: list[Path]):
    supported = {
        ".arw",
        ".cr2",
        ".cr3",
        ".nef",
        ".raf",
        ".fits",
        ".fit",
        ".fts",
        ".png",
        ".jpg",
        ".jpeg",
        ".tif",
        ".tiff",
    }
    for path in paths:
        if path.is_dir():
            for child in sorted(path.iterdir()):
                if child.suffix.lower() in supported:
                    yield child
        else:
            yield path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args(argv)

    for path in iter_paths(args.paths):
        image = load_info(path)
        array = load_image(image)
        finite = array[np.isfinite(array)]
        if finite.size == 0:
            print(f"{path}\tdtype={array.dtype}\tshape={array.shape}\tno finite pixels")
            continue
        print(
            f"{path}\tdtype={array.dtype}\tshape={array.shape}"
            f"\tmin={finite.min():.6g}\tmax={finite.max():.6g}\tmean={finite.mean():.6g}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
