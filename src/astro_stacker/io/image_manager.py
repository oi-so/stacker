"""Image memory management with LRU eviction."""

from collections import OrderedDict
from threading import RLock

import numpy as np

from .image_data import AstroImage
from .loader import load_image


class ImageManager:
    """Manages in-memory image data with automatic LRU eviction."""

    def __init__(self, max_loaded_image_count: int = 5) -> None:
        self.max_loaded_image_count = max_loaded_image_count

        # key=id(AstroImage), value=np.ndarray
        self._cache: OrderedDict[int, np.ndarray] = OrderedDict()
        self._lock = RLock()

    def __evict_if_needed(self) -> None:
        while len(self._cache) > self.max_loaded_image_count:
            self._cache.popitem(last=False)

    def get_image(self, image: AstroImage) -> np.ndarray:
        key = id(image)
        with self._lock:
            cached = self._cache.get(key)
            if cached is not None:
                self._cache.move_to_end(key)
                return cached
        loaded = load_image(image)
        with self._lock:
            cached = self._cache.get(key)

            if cached is not None:
                self._cache.move_to_end(key)
                return cached

            self._cache[key] = loaded
            self.__evict_if_needed()

            return loaded

    def load(self, image: AstroImage) -> None:
        self.get_image(image)

    def unload(self, image: AstroImage) -> None:
        key = id(image)

        with self._lock:
            self._cache.pop(key, None)

    def unload_all(self) -> None:
        with self._lock:
            self._cache.clear()

    def is_loaded(self, image: AstroImage) -> bool:
        with self._lock:
            return id(image) in self._cache

    def loaded_count(self) -> int:
        with self._lock:
            return len(self._cache)