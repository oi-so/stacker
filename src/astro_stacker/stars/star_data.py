from dataclasses import dataclass


@dataclass
class Star:
    x: float
    y: float

    flux: float
    peak: float

    sharpness: float | None = None

    roundness: float | None = None

    fwhm: float | None = None

    ellipticity: float | None = None



@dataclass
class StarCatalog:
    stars: list[Star]

    def brightest(self, n: int) -> list[Star]:
        return sorted(
            self.stars,
            key=lambda s: s.flux,
            reverse=True
        )[:n]