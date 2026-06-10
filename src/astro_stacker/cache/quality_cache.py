import json
from dataclasses import asdict

from ..io.image_data import ScoreData
from .manager import CacheManager


class QualityCache:
    def __init__(self, cache_manager: CacheManager):
        self.cache_manager = cache_manager

    def save(self, scores: dict[str, ScoreData]) -> None:
        data = {
            filename: asdict(score)
            for filename, score in scores.items()
        }

        with open(self.cache_manager.paths.quality, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)



    def load(self) -> dict[str, ScoreData]:
        path = self.cache_manager.paths.quality

        if not path.exists():
            return {}

        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        return {
            filename: ScoreData(**score)
            for filename, score in data.items()
        }