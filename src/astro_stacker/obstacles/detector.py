"""Conservative temporal obstacle-candidate detection.

Candidates are never masks until a user accepts them.  The detector favours
missing an obstruction over masking astronomy data by requiring a substantial,
time-variable, spatially connected signal.
"""

from __future__ import annotations

import cv2
import numpy as np

from .mask import MaskSource, ObstacleMask


class ObstacleDetector:
    def __init__(self, confidence_threshold: float = 0.6, minimum_area: int = 64):
        if not 0 <= confidence_threshold <= 1:
            raise ValueError("Confidence threshold must be between zero and one")
        self.confidence_threshold = confidence_threshold
        self.minimum_area = max(1, int(minimum_area))

    def detect(
        self,
        image: np.ndarray,
        reference_image: np.ndarray | None = None,
        aligned_images: list[np.ndarray] | None = None,
    ) -> list[ObstacleMask]:
        """Return unconfirmed, non-stellar temporal-change candidates.

        A single image deliberately produces no candidate: spatial features
        alone are too likely to be nebulosity, stars, or clouds.
        """
        if not aligned_images or len(aligned_images) < 3:
            return []
        current = self._luminance(image)
        samples = np.stack([self._luminance(item) for item in aligned_images], axis=0)
        if samples.shape[1:] != current.shape:
            raise ValueError("Aligned images must share the candidate image shape")
        median = np.median(samples, axis=0)
        mad = np.median(np.abs(samples - median), axis=0)
        deviation = np.abs(current - median) / (1.4826 * mad + 1e-6)
        # Saturate significance; an isolated point cannot pass the component
        # and morphology checks below, protecting normal stars.
        confidence = np.clip((deviation - 4.0) / 8.0, 0, 1).astype(np.float32)
        binary = (confidence >= self.confidence_threshold).astype(np.uint8)
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
        count, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
        candidates: list[ObstacleMask] = []
        for label in range(1, count):
            area = int(stats[label, cv2.CC_STAT_AREA])
            if area < self.minimum_area:
                continue
            component = labels == label
            candidates.append(
                ObstacleMask(component, confidence, label="unknown", source=MaskSource.AUTO)
            )
        return candidates

    @staticmethod
    def _luminance(image: np.ndarray) -> np.ndarray:
        data = np.asarray(image, dtype=np.float32)
        if data.ndim == 3:
            data = np.mean(data, axis=-1)
        if data.ndim != 2:
            raise ValueError("Obstacle detection expects a 2D or channel-last image")
        return np.nan_to_num(data, nan=0.0, posinf=0.0, neginf=0.0)
