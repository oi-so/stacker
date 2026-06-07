"""Image memory management with LRU eviction.

Manages loading and unloading of image data with configurable limits
to prevent excessive memory usage. Uses an OrderedDict to track LRU (Least
Recently Used) order for eviction.
"""

from collections import OrderedDict
import numpy as np

from .image_data import AstroImage, AstroImageInfo
from .loader import load_image


class ImageManager:
    """Manages in-memory image data with automatic eviction.
    
    When more images are loaded than max_loaded_image_count, the least
    recently used image is unloaded from memory.
    """
    def __init__(self, max_loaded_image_count: int = 5) -> None:
        """Initialize ImageManager.
        
        Args:
            max_loaded_image_count: Maximum number of images to keep in memory.
                                   Default is 5. Increase for systems with more RAM.
        """
        self.__loaded_images: OrderedDict[int, AstroImage] = OrderedDict()
        self.loaded_image_size = 0
        self.max_loaded_image_count = max_loaded_image_count

    def __evict_if_needed(self) -> None:
        """Remove least recently used images if cache exceeds max_loaded_image_count."""
        while len(self.__loaded_images) > self.max_loaded_image_count:
            _, image = self.__loaded_images.popitem(last=False)
            image.image = None
    

    def get_image(self, image: AstroImage) -> np.ndarray:
        """Get image data, loading from disk if necessary.
        
        Args:
            image: AstroImage object to retrieve
            
        Returns:
            Pixel data as numpy array
            
        Note:
            Updates LRU order and may evict other images if needed.
        """
        if image.image is None:
            image.image = load_image(image)

        key = id(image)
        if key in self.__loaded_images:
            # Move to end to mark as recently used
            self.__loaded_images.move_to_end(key)
        else:
            self.__loaded_images[key] = image

        self.__evict_if_needed()
        return image.image


    def load(self, image: AstroImage) -> None:
        """Load image data into memory (convenience method)."""
        self.get_image(image)


    def unload(self, image: AstroImage) -> None:
        """Unload image data from memory.
        
        Args:
            image: AstroImage object to unload
        """
        key = id(image)
        if key in self.__loaded_images:
            del self.__loaded_images[key]

        image.image = None


    def unload_all(self) -> None:
        """Unload all images from memory."""
        for image in self.__loaded_images.values():
            image.image = None
        self.__loaded_images.clear()


    def is_loaded(self, image: AstroImage) -> bool:
        """Check if image is currently in memory.
        
        Args:
            image: AstroImage object to check
            
        Returns:
            True if image data is loaded
        """
        return id(image) in self.__loaded_images
    

    def loaded_count(self) -> int:
        """Get number of images currently in memory.
        
        Returns:
            Count of loaded images
        """
        return len(self.__loaded_images)
