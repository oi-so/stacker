from abc import ABC, abstractmethod
from ..io.image_data import AstroImage

from .result import PlateSolveResult


class PlateSolver(ABC):
    @abstractmethod
    def solve(self, image: AstroImage) -> PlateSolveResult:
        pass


    @abstractmethod
    def is_available(self) -> bool:
        pass