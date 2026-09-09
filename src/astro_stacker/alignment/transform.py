"""Apply alignment transformations to images."""

import numpy as np
import cv2

from ..core.frame_provider import FrameProvider
from ..io.image_data import AstroImage, ColorMode, TransformData


class ImageTransformer:
    @staticmethod
    def _warp(image: np.ndarray, matrix: np.ndarray) -> np.ndarray:
        height, width = image.shape[:2]
        return cv2.warpAffine(
            np.asarray(image, dtype=np.float32),
            np.asarray(matrix[:2], dtype=np.float64), (width, height),
            flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0,
        )

    def _transform_rgb(self, image: np.ndarray, transform: TransformData) -> np.ndarray:
        return self._warp(image, transform.matrix)

    def _transform_mono(self, image: np.ndarray, transform: TransformData) -> np.ndarray:
        return self._warp(image[..., 0], transform.matrix)[..., np.newaxis]

    def _transform_bayer(self, image: np.ndarray, transform: TransformData) -> np.ndarray:
        mono = image[..., 0]
        transformed = np.empty_like(mono, dtype=np.float32)
        for y in range(2):
            for x in range(2):
                # A Bayer plane lives at full-image coordinates 2*p + offset.
                # Conjugate the transform to preserve its colour and origin.
                matrix = np.array(transform.matrix, dtype=np.float64, copy=True)
                offset = np.array([x, y], dtype=np.float64)
                matrix[:2, 2] = (
                    matrix[:2, 2] + matrix[:2, :2] @ offset - offset
                ) / 2.0
                plane = mono[y::2, x::2]
                if plane.size:
                    transformed[y::2, x::2] = self._warp(plane, matrix)
        return transformed[..., np.newaxis]

    def apply_transform(
        self,
        image: np.ndarray,
        astro_image: AstroImage,
        transform: TransformData | None = None,
    ) -> np.ndarray:
        """Apply pre-computed transformation to an image.
        
        Args:
            image: Input image array
            astro_image: AstroImage containing transformation information
            
        Returns:
            Transformed image with same dtype as input
        """

        if transform is None:
            transform = astro_image.info.transform

        if transform is None or transform.matrix is None:
            return image.astype(np.float32, copy=False)


        if np.array_equal(transform.matrix, np.eye(3)):
            return image.astype(np.float32, copy=False)

        # RGB画像
        if image.ndim == 3 and image.shape[2] == 3:
            return self._transform_rgb(image, transform)

        # 1チャンネル画像
        if image.ndim == 3 and image.shape[2] == 1:
            if astro_image.info.color_mode == ColorMode.BAYER:
                return self._transform_bayer(image, transform)
            else:
                return self._transform_mono(image, transform)

        # 2次元画像
        if image.ndim == 2:
            if astro_image.info.color_mode == ColorMode.BAYER:
                return self._transform_bayer(image[..., np.newaxis], transform)
            else:
                return self._transform_mono(image[..., np.newaxis], transform)

        raise ValueError(f"Unsupported image shape {image.shape} for transformation.")



class AlignedFrameProvider:
    def __init__(self, base_provider: FrameProvider, transformer: ImageTransformer) -> None:
        self.base_provider = base_provider
        self.transformer = transformer


    def get_image(self, astro_image: AstroImage) -> np.ndarray:
        image = self.base_provider.get_image(astro_image)

        transform = astro_image.info.transform
        if transform is None:
            return image.astype(np.float32, copy=False)
        
        image = self.transformer.apply_transform(image, astro_image)
        return image
