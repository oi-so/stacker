"""Star catalog data structures."""

from dataclasses import dataclass


@dataclass(slots=True)
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



@dataclass(slots=True)
class StarCatalog:
    """Collection of stars from an image.
    
    Attributes:
        stars: List of detected Star objects
    """
    stars: list[Star]

    def brightest(self, n: int) -> "StarCatalog":
        """Get the N brightest stars (by flux).
        
        Args:
            n: Number of stars to return
            
        Returns:
            List of up to N brightest stars, sorted by flux (descending)
        """
        return StarCatalog(sorted(
            self.stars,
            key=lambda s: s.flux,
            reverse=True
        )[:n])

    def point_sources(
        self,
        n: int,
        *,
        minimum_sharpness: float = 0.20,
        maximum_abs_roundness: float = 0.50,
        width: int | None = None,
        height: int | None = None,
        grid_size: int = 6,
        min_separation: float | None = None,
    ) -> "StarCatalog":
        """Return bright, point-like candidates suitable for alignment."""
        candidates = [
            star
            for star in self.stars
            if star.sharpness is not None
            and star.roundness is not None
            and star.sharpness >= minimum_sharpness
            and abs(star.roundness) <= maximum_abs_roundness
        ]
        candidates.sort(key=lambda star: star.flux, reverse=True)

        if not candidates:
            return StarCatalog(candidates[:n])

        if min_separation is None:
            # Only needs to be large enough to collapse a single dense
            # cluster (e.g. a bright nebula core, which is typically a few
            # tens of pixels across) down to one anchor. It must NOT scale
            # with the frame size -- tying it to width/height/grid_size
            # turns this into a coarse whole-frame grid again and throws
            # away the vast majority of ordinary, well-separated real stars
            # (verified: on a 6022x4024 frame this previously forced ~500px
            # spacing and cut 1400 real detections down to ~70 candidates).
            min_separation = 25.0

        min_sep_sq = min_separation ** 2
        selected: list[Star] = []
        for star in candidates:
            if len(selected) >= n:
                break
            if all(
                (star.x - s.x) ** 2 + (star.y - s.y) ** 2 >= min_sep_sq
                for s in selected
            ):
                selected.append(star)

        return StarCatalog(selected)