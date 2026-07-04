# Astro Stacker Specification

> 注意: この文書は古い仕様メモを含みます。現行実装の基準は `docs/SPEC.md` と
> `PROJECT_GUIDE.md` です。特に `AstroImage.load()/unload()`、旧 calibration クラス名、
> 「高レベル統合が未配線」という記述は現行コードと一致しません。

## Overview
Astro Stacker is an astronomical image processing application for stacking, calibration, alignment, and output of astrophotography images. The current implementation contains core I/O, image caching, and calibration scaffolding.

## Architecture
The project is organized into several functional packages under `src/astro_stacker`:

- `io`: Image loading, metadata handling, and caching.
- `calibration`: Calibration frame handling and image correction scaffolding.
- `alignment`: Alignment algorithms and transform data.
- `stacking`: Frame combination strategies.
- `drizzle`: Resampling and drizzle processing.
- `platesolve`: Plate solving and WCS metadata.
- `quality`: Frame scoring and selection.
- `ui`: User interface components.

## Data Models
The core image data model is `AstroImage`.

### `AstroImageInfo`
Fields:
- `path: Path` — source file path.
- `shape: ImageShape` — width, height, channels.
- `bit_depth: int`
- `exposure_time: float | None`
- `iso: int | None`
- `f_number: float | None`
- `exif: dict | None`
- `wcs: WCSData | None`
- `score_data: ScoreData | None`
- `transform: TransformData | None`

### `AstroImage`
Fields:
- `info: AstroImageInfo`
- `image: np.ndarray | None`

Properties and methods:
- `is_loaded` — `True` when `image` is not `None`.
- `load()` — loads pixel data from disk if not already loaded.
- `unload()` — releases pixel data.

## I/O Module
Module: `src/astro_stacker/io/loader.py`

### `load_info(path: Path) -> AstroImage`
- Detects file type by extension.
- Supports RAW and FITS via dedicated loaders.
- For other image types, delegates to standard image readers.
- Returns an `AstroImage` instance whose `image` field is initially `None`.

### `load_image(astro_image: AstroImage) -> np.ndarray`
- Loads pixel data from the underlying file path.
- Uses the same extension-based dispatch as `load_info`.
- Returns a NumPy array.

### Supported extensions
- RAW: `.cr2`, `.nef`, `.arw`, `.dng`, `.rw2`, `.orf`, `.raf`, `.pef`, `.srw`, `.srf`, `.sr2`, `.kdc`, `.mos`, `.mrw`, `.mef`, `.erf`, `.x3f`, `.bay`, `.cap`, `.iiq`, `.rwl`, `.raw`
- FITS: `.fits`, `.fit`, `.fts`

### `ImageManager`
Module: `src/astro_stacker/io/image_manager.py`

Responsibilities:
- Cache loaded images in memory.
- Keep at most `max_loaded_image_count` images loaded simultaneously.
- Evict the least-recently-used image when the cache limit is exceeded.

API:
- `get_image(image: AstroImage) -> np.ndarray`
  - Loads the image if not already loaded.
  - Updates cache order to implement LRU behavior.
  - Returns the NumPy image array.
- `load(image: AstroImage) -> None`
  - Ensures the image is loaded into memory.
- `unload(image: AstroImage) -> None`
  - Removes a specific image from the cache and frees its data.
- `unload_all() -> None`
  - Clears the cache and releases all loaded pixel arrays.
- `is_loaded(image: AstroImage) -> bool`
  - Returns whether the image is currently cached.
- `loaded_count() -> int`
  - Returns the number of cached images.

## Calibration Module
Module: `src/astro_stacker/calibration/calibration.py`

This module currently provides calibration frame data structures and a simple correction pipeline. Most implementation details are scaffolded rather than finalized.

### Data classes
#### `CalibrationFrameSet`
- `darks: list[Path] | None`
- `biases: list[Path] | None`
- `flats: list[Path] | None`
- `flat_darks: list[Path] | None`

Used to hold file paths for each type of calibration frame.

#### `CalibrationMasterFrames`
- `dark: np.ndarray | None`
- `bias: np.ndarray | None`
- `flat: np.ndarray | None`
- `flat_dark: np.ndarray | None`

Represents prepared master calibration frames.

### `CalibrationPipeline`
Controls which calibration steps are applied:
- `use_darks: bool`
- `use_biases: bool`
- `use_flats: bool`
- `use_flat_darks: bool`

### `Calibrator`
- Constructor: `Calibrator(master: CalibrationMasterFrames, pipeline: CalibrationPipeline)`
- Method: `calibrate(image: np.ndarray) -> np.ndarray`

Current behavior:
- Converts input to `np.float32`.
- Subtracts `dark` when `use_darks` is enabled.
- Subtracts `bias` when `use_biases` is enabled.
- Applies flat-field correction when `use_flats` is enabled.
- Applies flat-dark subtraction from the flat frame when `use_flat_darks` is enabled.

#### Bug fix
- Previously, flat-dark subtraction incorrectly used `master.dark` instead of `master.flat_dark`. This has been corrected.

### `MasterFrameBuilder`
- Constructor: `MasterFrameBuilder(manager: ImageManager)`
- Method: `build(images: list[AstroImage], method: str = "median") -> np.ndarray`

Builds a master calibration frame by loading each source image through `ImageManager` and stacking them.
Supported methods:
- `median`
- `mean`

### Placeholder
- `sigma_clip()` is currently a stub and returns `None`.

## Package Exports
Module: `src/astro_stacker/calibration/__init__.py`

Exports:
- `Calibrator`
- `CalibrationFrameSet`
- `CalibrationMasterFrames`
- `CalibrationPipeline`
- `MasterFrameBuilder`
- `CalibrationResult`
- `CalibrationManager`
- `DarkCalibrator`
- `FlatCalibrator`
- `BiasCalibrator`
- `FlatDarkCalibrator`

## Usage Examples

### Loading image metadata and pixel data
```python
from pathlib import Path
from astro_stacker.io.loader import load_info
from astro_stacker.io.image_manager import ImageManager

path = Path("/path/to/image.fits")
astro_image = load_info(path)
manager = ImageManager(max_loaded_image_count=5)
image_array = manager.get_image(astro_image)
```

### Using the image cache
```python
manager.load(astro_image)
assert manager.is_loaded(astro_image)
manager.unload(ast_img)
manager.unload_all()
```

### Building a master frame
```python
from astro_stacker.calibration.calibration import MasterFrameBuilder

builder = MasterFrameBuilder(manager)
master_flat = builder.build(flat_images, method="median")
```

### Running calibration
```python
from astro_stacker.calibration.calibration import (
    CalibrationMasterFrames,
    CalibrationPipeline,
    Calibrator,
)

master_frames = CalibrationMasterFrames(
    dark=dark_stack,
    bias=bias_stack,
    flat=flat_stack,
    flat_dark=flat_dark_stack,
)

pipeline = CalibrationPipeline(
    use_darks=True,
    use_biases=True,
    use_flats=True,
    use_flat_darks=True,
)

calibrator = Calibrator(master=master_frames, pipeline=pipeline)
calibrated_image = calibrator.calibrate(raw_image)
```

## Current Implementation Notes
- `ImageManager` implements a simple LRU cache by image object identity.
- Calibration is currently scaffolded; core numerical algorithms are present only in a basic prototype form.
- The `calibration` package is available, but higher-level integration with the stacking pipeline is not yet wired in.

## Future Work
- Implement full master frame creation and outlier rejection.
- Add support for dark, flat, bias, and flat-dark frame preparation from raw files.
- Add calibration integration into the main stacking pipeline.
- Implement `sigma_clip()` and advanced normalization options.
