import json
from dataclasses import asdict
from pathlib import Path

from .models import CacheInfo, CachePaths


class CacheManager:
    def __init__(self, cache_dir: Path):
        self.paths = CachePaths(cache_dir)

        self.paths.root.mkdir(
            parents=True,
            exist_ok=True
        )

    def save_cache_info(self, cache_info: CacheInfo) -> None:
        with open(self.paths.cache_info, "w", encoding="utf-8") as f:
            json.dump(asdict(cache_info), f, indent=4)

    def load_cache_info(self) -> CacheInfo | None:
        if not self.paths.cache_info.exists():
            return None

        with open(
            self.paths.cache_info,
            encoding="utf-8"
        ) as f:
            data = json.load(f)

        return CacheInfo(**data)