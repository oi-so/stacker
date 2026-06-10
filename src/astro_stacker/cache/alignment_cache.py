import json
from dataclasses import asdict

from ..io.image_data import TransformData
from .manager import CacheManager


class AlignmentCache:
    def __init__(self, cache_manager: CacheManager):
        self.cache_manager = cache_manager

    def save(self, transforms: dict[str, TransformData]) -> None:
        data = {
            filename: asdict(transform)
            for filename, transform in transforms.items()
        }

        with open(self.cache_manager.paths.alignment, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)

    def load(self) -> dict[str, TransformData]:

        path = self.cache_manager.paths.alignment

        if not path.exists():
            return {}

        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        return {
            filename: TransformData(**transform)
            for filename, transform in data.items()
        }