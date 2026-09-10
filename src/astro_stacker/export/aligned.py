"""Non-destructive aligned-frame export using existing image savers."""

from pathlib import Path

import numpy as np

from ..core.frame_provider import FrameProvider
from ..io.image_data import AstroImage
from ..io.saver import save_image
from ..masks.weights import AlignmentValidityMaskProvider, WeightMaskProvider, validity_mask
from ..project.settings import InvalidPixelPolicy


def export_aligned_frames(
    frames: list[AstroImage],
    provider: FrameProvider,
    output_directory: Path,
    *,
    suffix: str = ".fits",
    bit_depth: int | str | None = None,
    mask_provider: WeightMaskProvider | None = None,
    invalid_pixels: InvalidPixelPolicy = InvalidPixelPolicy.ZERO,
    save_validity_masks: bool = False,
    include_alignment_footprint: bool = True,
    progress=None,
    is_cancelled=None,
) -> list[Path]:
    """Write every provider-produced frame; source files are never touched."""
    if not suffix.startswith("."):
        suffix = "." + suffix
    output_directory.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    alignment_masks = AlignmentValidityMaskProvider()
    for index, frame in enumerate(frames, 1):
        if is_cancelled and is_cancelled():
            break
        image = np.asarray(provider.get_image(frame), dtype=np.float32)
        mask = validity_mask(image)
        if include_alignment_footprint and frame.info.is_aligned:
            mask *= alignment_masks.get_mask(frame, image.shape[:2])
        if mask_provider is not None:
            mask *= mask_provider.get_mask(frame, image.shape[:2])
        invalid = mask <= 0
        if np.any(invalid):
            image = image.copy()
            fill = np.nan if invalid_pixels == InvalidPixelPolicy.NAN else 0.0
            if image.ndim == 3:
                image[invalid, :] = fill
            else:
                image[invalid] = fill
        path = output_directory / f"{frame.info.path.stem}_aligned{suffix}"
        serial = 2
        while path.exists():
            path = output_directory / f"{frame.info.path.stem}_aligned_{serial}{suffix}"
            serial += 1
        save_image(image, path, bit_depth=bit_depth, metadata=frame.info.exif or {})
        paths.append(path)
        if save_validity_masks or invalid_pixels == InvalidPixelPolicy.KEEP_MASK:
            mask_path = output_directory / f"{frame.info.path.stem}_aligned_mask{suffix}"
            save_image(mask, mask_path, bit_depth=bit_depth, frame_type="validity_mask")
            paths.append(mask_path)
        if progress:
            progress("位置合わせ画像を書き出し中", index, len(frames), path.name)
    return paths
