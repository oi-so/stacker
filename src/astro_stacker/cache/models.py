from dataclasses import dataclass
from pathlib import Path


@dataclass
class CacheInfo:
    astro_stacker_version: str = "0.1.0"
    cache_version: int = 1


@dataclass
class CachePaths:
    root: Path

    @property
    def cache_info(self) -> Path:
        return self.root / "cache_info.json"

    @property
    def alignment(self) -> Path:
        return self.root / "alignment.json"

    @property
    def quality(self) -> Path:
        return self.root / "quality.json"

    @property
    def master_dark(self) -> Path:
        return self.root / "master_dark.fits"

    @property
    def master_flat(self) -> Path:
        return self.root / "master_flat.fits"

    @property
    def master_bias(self) -> Path:
        return self.root / "master_bias.fits"

    @property
    def master_flat_dark(self) -> Path:
        return self.root / "master_flat_dark.fits"