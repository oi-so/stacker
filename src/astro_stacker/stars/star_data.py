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
    ) -> "StarCatalog":
        """Return bright, point-like candidates suitable for alignment.

        DAOStarFinder also reports compact knots in bright nebulae.  Those
        detections are useful for image-quality inspection but are unstable
        alignment anchors, especially in HDR's darker exposures.
        """
        candidates = [
            star
            for star in self.stars
            if star.sharpness is not None
            and star.roundness is not None
            and star.sharpness >= minimum_sharpness
            and abs(star.roundness) <= maximum_abs_roundness
        ]
        candidates.sort(key=lambda star: star.flux, reverse=True)
        if width is None or height is None or len(candidates) <= n:
            return StarCatalog(candidates[:n])

        # Pick one strong candidate per occupied cell before filling the
        # remaining budget. This prevents a bright nebula core from consuming
        # every alignment slot and keeps outer-field stars available.
        grid_size = max(1, int(grid_size))
        cells: dict[tuple[int, int], list[Star]] = {}
        for star in candidates:
            column = min(grid_size - 1, max(0, int(star.x / width * grid_size)))
            row = min(grid_size - 1, max(0, int(star.y / height * grid_size)))
            cells.setdefault((row, column), []).append(star)

        selected: list[Star] = []
        for cell in cells.values():
            if len(selected) >= n:
                break
            selected.append(cell[0])
        selected_ids = {id(star) for star in selected}
        for star in candidates:
            if len(selected) >= n:
                break
            if id(star) not in selected_ids:
                selected.append(star)
                selected_ids.add(id(star))
        return StarCatalog(selected)