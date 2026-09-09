"""Apply alignment transformations to images."""

import numpy as np
from skimage.transform import SimilarityTransform, warp

from ..core.frame_provider import FrameProvider
from ..io.image_data import AstroImage, ColorMode, TransformData


class ImageTransformer:
    def _transform_rgb(self, image: np.ndarray, transform: TransformData) -> np.ndarray:
        t = SimilarityTransform(matrix=transform.matrix)
        return warp(image, inverse_map=t.inverse, preserve_range=True).astype(np.float32)
    

    def _transform_mono(self, image: np.ndarray, transform: TransformData) -> np.ndarray:
        t = SimilarityTransform(matrix=transform.matrix)
        warped = warp(image[..., 0], inverse_map=t.inverse, preserve_range=True)
        return warped[..., np.newaxis].astype(np.float32)
    

    def _transform_bayer(self, image: np.ndarray, transform: TransformData) -> np.ndarray:
        mono = image[..., 0]

        # 2. RAW画像（2次元配列）の場合：CFA（Bayer）分離アプローチを適用
        # 2x2のピクセルパターンをR, G1, G2, Bの4つのサブ画像（サイズは縦横半分）に分離
        ch00 = mono[0::2, 0::2]
        ch01 = mono[0::2, 1::2]
        ch10 = mono[1::2, 0::2]
        ch11 = mono[1::2, 1::2]

        # サブ画像はサイズが半分になっているため、アライメント行列の平行移動成分（dx, dy）も半分にする
        matrix_half = transform.matrix.copy()
        matrix_half[0, 2] /= 2.0  # x方向の移動量を半分に
        matrix_half[1, 2] /= 2.0  # y方向の移動量を半分に
        t_half = SimilarityTransform(matrix=matrix_half)

        # それぞれのチャンネル単色でWarpを適用
        w_ch00 = warp(ch00, inverse_map=t_half.inverse, preserve_range=True)
        w_ch01 = warp(ch01, inverse_map=t_half.inverse, preserve_range=True)
        w_ch10 = warp(ch10, inverse_map=t_half.inverse, preserve_range=True)
        w_ch11 = warp(ch11, inverse_map=t_half.inverse, preserve_range=True)

        # 変形後のサブ画像を、元の格子状（ベイヤー配列）の配置に組み立て直す
        transformed = np.empty_like(mono, dtype=np.float32)
        transformed[0::2, 0::2] = w_ch00
        transformed[0::2, 1::2] = w_ch01
        transformed[1::2, 0::2] = w_ch10
        transformed[1::2, 1::2] = w_ch11

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

        if transform is None:
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
