import json
from dataclasses import asdict

from .models import CacheInfo, CachePaths
from ..project.project import Project
from ..io.image_data import ScoreData, AlignmentData, TransformData


class CacheManager:
    def __init__(self, project: Project):
        self.project = project
        if self.project.cache_directory is None:
            raise ValueError("Project.cache_directory is none.")
        self.paths = CachePaths(self.project.cache_directory)

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
    


    def save_quality(self):
        images = self.project.light_frames
        data = {}

        for image in images:
            data[str(image.info.path.resolve())] = {
                "score_data": (
                    image.info.score_data.to_dict()
                ),
            }

        with open(self.paths.alignment, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)


    def load_quality(self) -> bool:
        images = self.project.light_frames
        
        if not self.paths.alignment.exists():
            return False
        
        with open(self.paths.alignment, encoding="utf-8") as f:
            data = json.load(f)

        for image in images:
            key = str(image.info.path.resolve())
            if key not in data: continue

            image.info.score_data = ScoreData.from_dict(data[key]["score_data"])

        return True

    def save_alignment(self):
        images = self.project.light_frames
        data = {}

        for image in images:
            data[str(image.info.path.resolve())] = {
                "transform": (
                    image.info.transform.to_dict()
                ),
                "alignment_data": (
                    image.info.alignment_data.to_dict()
                ),
            }

        with open(self.paths.alignment, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)


    def load_alignment(self):
        images = self.project.light_frames
        
        if not self.paths.alignment.exists():
            return False
        
        with open(self.paths.alignment, encoding="utf-8") as f:
            data = json.load(f)

        for image in images:
            key = str(image.info.path.resolve())
            if key not in data: continue

            image.info.transform = (
                TransformData.from_dict(
                    data[key]["transform"]
                )
            )

            image.info.alignment_data = (
                AlignmentData.from_dict(
                    data[key]["alignment_data"]
                )
            )

        return True
    