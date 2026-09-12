"""Byte-bounded image LRU with file invalidation and shared concurrent loads."""

from collections import OrderedDict
from concurrent.futures import Future
from threading import RLock

import numpy as np

from ..core.resources import IMAGE_CACHE_BYTES
from .image_data import AstroImage
from .loader import load_image


class ImageManager:
    def __init__(
        self, max_loaded_image_count: int = 10, max_cache_bytes: int = IMAGE_CACHE_BYTES
    ) -> None:
        self.max_loaded_image_count = max(0, max_loaded_image_count)
        self.max_cache_bytes = max(0, max_cache_bytes)
        self._cache = OrderedDict()
        self._pending = {}
        self._bytes = 0
        self._generation = 0
        self._lock = RLock()

    @staticmethod
    def cache_key(image: AstroImage):
        path = image.info.path.resolve()
        stat = path.stat()
        return str(path), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns

    @property
    def cached_bytes(self) -> int:
        with self._lock:
            return self._bytes

    def get_image(self, image: AstroImage) -> np.ndarray:
        key = self.cache_key(image)
        with self._lock:
            cached = self._cache.get(key)
            if cached is not None:
                self._cache.move_to_end(key)
                return cached
            generation = self._generation
            pending_key = (generation, key)
            pending = self._pending.get(pending_key)
            owner = pending is None
            if owner:
                pending = self._pending[pending_key] = Future()
        if not owner:
            return pending.result()
        try:
            loaded = load_image(image)
            with self._lock:
                if generation == self._generation:
                    for old in list(self._cache):
                        if old[0] == key[0]:
                            self._bytes -= self._cache.pop(old).nbytes
                    if loaded.nbytes <= self.max_cache_bytes and self.max_loaded_image_count:
                        while self._cache and (
                            self._bytes + loaded.nbytes > self.max_cache_bytes
                            or len(self._cache) >= self.max_loaded_image_count
                        ):
                            self._bytes -= self._cache.popitem(last=False)[1].nbytes
                        self._cache[key] = loaded
                        self._bytes += loaded.nbytes
            pending.set_result(loaded)
            return loaded
        except BaseException as exc:
            pending.set_exception(exc)
            raise
        finally:
            with self._lock:
                self._pending.pop(pending_key, None)

    def configure_cache(self, max_cache_bytes: int) -> None:
        with self._lock:
            self.max_cache_bytes = max(0, int(max_cache_bytes))
            while self._cache and self._bytes > self.max_cache_bytes:
                self._bytes -= self._cache.popitem(last=False)[1].nbytes

    def load(self, image: AstroImage) -> None:
        self.get_image(image)

    def unload(self, image: AstroImage) -> None:
        path = str(image.info.path.resolve())
        with self._lock:
            self._generation += 1
            for key in list(self._cache):
                if key[0] == path:
                    self._bytes -= self._cache.pop(key).nbytes

    def unload_all(self) -> None:
        with self._lock:
            self._generation += 1
            self._cache.clear()
            self._bytes = 0

    def is_loaded(self, image: AstroImage) -> bool:
        try:
            key = self.cache_key(image)
        except OSError:
            return False
        with self._lock:
            return key in self._cache

    def loaded_count(self) -> int:
        with self._lock:
            return len(self._cache)
