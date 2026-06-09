from dataclasses import dataclass
import numpy as np



@dataclass
class PipelineResult:
    image: np.ndarray
    aligned_count: int
    average_rms_error: float