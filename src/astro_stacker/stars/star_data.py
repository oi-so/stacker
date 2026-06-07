"""Star catalog data structures."""

from dataclasses import dataclass


@dataclass
class Star:
    """A detected star with centroid and photometry.
    
    Attributes:
        x: X centroid in pixels
        y: Y centroid in pixels
        flux: Total integrated flux
        peak: Peak pixel value
        sharpness: Sharpness metric (high = point-like)
        roundness: Roundness metric (0 = circular)
        fwhm: Full Width at Half Maximum in pixels (calculated separately)
        ellipticity: Ellipticity (0 = circular, 1 = very elongated)
    """
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
    """Collection of stars from an image.
    
    Attributes:
        stars: List of detected Star objects
    """
    stars: list[Star]

    def brightest(self, n: int) -> list[Star]:
        """Get the N brightest stars (by flux).
        
        Args:
            n: Number of stars to return
            
        Returns:
            List of up to N brightest stars, sorted by flux (descending)
        """
        return sorted(
            self.stars,
            key=lambda s: s.flux,
            reverse=True
        )[:n]