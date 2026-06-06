from collections import OrderedDict
import numpy as np

from .image_data import AstroImage
from .loader import load_image


class ImageManager:
    def __init__(self, max_loaded_image_count: int = 5) -> None:
        self.__loaded_images: OrderedDict[int, AstroImage] = OrderedDict()
        self.loaded_image_size = 0
        self.max_loaded_image_count = max_loaded_image_count

    def __evict_if_needed(self) -> None:
        while len(self.__loaded_images) > self.max_loaded_image_count:
            _, image = self.__loaded_images.popitem(last=False)
            image.image = None
    

    def get_image(self, image: AstroImage) -> np.ndarray:
        if image.image is not None:
            image.image = load_image(image)

        key = id(image)
        if key in self.__loaded_images:
            self.__loaded_images.move_to_end(key)
        else:
            self.__loaded_images[key] = image

        self.__evict_if_needed()
        return image.image


    def load(self, image: AstroImage) -> None:
        self.get_image(image)


    def unload(self, image: AstroImage) -> None:
        key = id(image)
        if key in self.__loaded_images:
            del self.__loaded_images[key]

        image.image = None


    def unload_all(self) -> None:
        for image in self.__loaded_images.values():
            image.image = None
        self.__loaded_images.clear()


    def is_loaded(self, image: AstroImage) -> bool:
        return id(image) in self.__loaded_images
    

    def loaded_count(self) -> int:
        return len(self.__loaded_images)
    


    