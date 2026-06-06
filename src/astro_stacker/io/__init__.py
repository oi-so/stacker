"""
I/O module for Astro Stacker
"""

from .image_manager import ImageManager
from .image_data import AstroImage, AstroImageInfo
from .loader import load_image
__all__ = [
    "ImageManager",
    "AstroImage",
    "AstroImageInfo",
    "load_image",
]