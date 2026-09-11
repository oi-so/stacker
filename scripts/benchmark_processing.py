"""Repeatable synthetic benchmark; run with `uv run python scripts/benchmark_processing.py`."""

import argparse
import json
import statistics
import time
from pathlib import Path

import numpy as np

from astro_stacker.alignment.detection import process_frame
from astro_stacker.alignment.transform import ImageTransformer
from astro_stacker.io.image_data import (
    AstroImage,
    AstroImageInfo,
    ColorMode,
    ImageShape,
    TransformData,
)
from astro_stacker.io.loader import load_image, load_info
from astro_stacker.project.settings import StackingMethod
from astro_stacker.stacking.combiner import ImageCombiner


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, help="Optional RAW image for loading timings")
    parser.add_argument("--repeat", type=int, default=3)
    args = parser.parse_args()
    if args.repeat < 1:
        parser.error("--repeat must be at least 1")
    rng = np.random.default_rng(42)
    image = rng.normal(100, 3, (1024, 1536, 1)).astype("float32")
    yy, xx = np.mgrid[-7:8, -7:8]
    for x, y in rng.integers([12, 12], [1524, 1012], size=(100, 2)):
        image[y - 7 : y + 8, x - 7 : x + 8, 0] += 500 * np.exp(-(xx * xx + yy * yy) / 4)
    frame = AstroImage(
        AstroImageInfo(Path("synthetic.fit"), ImageShape(1536, 1024, 1), 16, ColorMode.MONO)
    )
    frame.info.transform = TransformData(
        matrix=np.array([[1.0, 0.0, 2.3], [0.0, 1.0, -1.7], [0.0, 0.0, 1.0]])
    )

    class Provider:
        def get_image(self, _frame):
            return image

    provider = Provider()
    operations = {
        "star_detection": lambda: process_frame(provider, frame, 5, 500),
        "image_warp": lambda: ImageTransformer().apply_transform(image, frame),
        "average_12": lambda: ImageCombiner(provider).combine([frame] * 12, StackingMethod.AVERAGE),
        "median_12": lambda: ImageCombiner(provider).combine([frame] * 12, StackingMethod.MEDIAN),
        "sigma_clip_12": lambda: ImageCombiner(provider).combine(
            [frame] * 12, StackingMethod.SIGMA_CLIP
        ),
    }
    if args.raw:
        raw_frame = load_info(args.raw)
        operations["raw_metadata"] = lambda: load_info(args.raw)
        operations["raw_pixels"] = lambda: load_image(raw_frame)
    times = {}
    for name, operation in operations.items():
        operation()  # Warm imports, native kernels and filesystem cache.
        samples = []
        for _ in range(args.repeat):
            start = time.perf_counter()
            operation()
            samples.append(time.perf_counter() - start)
        times[name] = round(statistics.median(samples), 6)
    print(
        json.dumps(
            {
                "shape": list(image.shape),
                "frames": 12,
                "repeats": args.repeat,
                "median_seconds": times,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
