"""Feature-based alignment for terrestrial regions."""

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class GroundAlignmentResult:
    matrix: np.ndarray
    match_count: int
    inlier_count: int
    rms_error: float


def _gray8(image: np.ndarray) -> np.ndarray:
    data = np.asarray(image, dtype=np.float32)
    if data.ndim == 3:
        data = cv2.cvtColor(data, cv2.COLOR_RGB2GRAY) if data.shape[-1] == 3 else data[..., 0]
    finite = data[np.isfinite(data)]
    if not finite.size:
        return np.zeros(data.shape, dtype=np.uint8)
    low, high = np.percentile(finite, (1, 99))
    return (np.clip((data - low) / max(high - low, 1e-8), 0, 1) * 255).astype(np.uint8)


class GroundAligner:
    def __init__(self, detector: str = "orb", model: str = "similarity"):
        self.detector_name = detector.lower()
        self.model = model.lower()
        if self.detector_name == "sift":
            self.detector = cv2.SIFT_create(nfeatures=4000)
            self.norm = cv2.NORM_L2
        elif self.detector_name == "akaze":
            self.detector = cv2.AKAZE_create()
            self.norm = cv2.NORM_HAMMING
        elif self.detector_name == "orb":
            self.detector = cv2.ORB_create(nfeatures=4000)
            self.norm = cv2.NORM_HAMMING
        else:
            raise ValueError(f"Unknown ground feature detector: {detector}")
        if self.model not in {"translation", "similarity", "affine", "homography"}:
            raise ValueError(f"Unknown ground transform model: {model}")

    def align(
        self, image: np.ndarray, reference: np.ndarray, ground_mask: np.ndarray | None = None
    ) -> GroundAlignmentResult:
        source = _gray8(image)
        target = _gray8(reference)
        mask = None
        if ground_mask is not None:
            mask = (np.asarray(ground_mask) > 0.5).astype(np.uint8) * 255
            if mask.shape != source.shape:
                raise ValueError("Ground feature mask shape does not match image")
        kp1, des1 = self.detector.detectAndCompute(source, mask)
        kp2, des2 = self.detector.detectAndCompute(target, mask)
        if des1 is None or des2 is None:
            raise ValueError("Ground alignment found too few features")
        pairs = cv2.BFMatcher(self.norm).knnMatch(des1, des2, k=2)
        matches = [a for a, b in pairs if a.distance < 0.75 * b.distance]
        minimum = 4 if self.model == "homography" else 3
        if len(matches) < minimum:
            raise ValueError(f"Ground alignment found only {len(matches)} reliable matches")
        src = np.float32([kp1[m.queryIdx].pt for m in matches])
        dst = np.float32([kp2[m.trainIdx].pt for m in matches])
        if self.model == "homography":
            matrix, inliers = cv2.findHomography(src, dst, cv2.RANSAC, 3.0)
        elif self.model == "affine":
            affine, inliers = cv2.estimateAffine2D(src, dst, method=cv2.RANSAC)
            matrix = None if affine is None else np.vstack([affine, [0, 0, 1]])
        elif self.model == "translation":
            delta = np.median(dst - src, axis=0)
            matrix = np.array([[1, 0, delta[0]], [0, 1, delta[1]], [0, 0, 1]], dtype=float)
            error = np.linalg.norm((src + delta) - dst, axis=1)
            inliers = (error <= 3.0).astype(np.uint8)[:, None]
        else:
            affine, inliers = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC)
            matrix = None if affine is None else np.vstack([affine, [0, 0, 1]])
        if matrix is None or inliers is None:
            raise ValueError("Ground alignment transform estimation failed")
        projected = cv2.perspectiveTransform(src[:, None, :], matrix)[:, 0, :]
        keep = inliers.ravel().astype(bool)
        rms = float(np.sqrt(np.mean(np.sum((projected[keep] - dst[keep]) ** 2, axis=1))))
        return GroundAlignmentResult(matrix.astype(np.float64), len(matches), int(keep.sum()), rms)
