from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from astropy.time import Time

from .models import CatalogObject, SkyPosition


def _is_comet(target: CatalogObject) -> bool:
    kind = (target.kind or "").strip().lower()
    designation = target.designation.strip().upper()
    return kind.startswith("c") or "/" in designation or (
        designation[:-1].isdigit() and designation.endswith("P")
    )


class HorizonsEphemeris:
    """Calculate apparent ICRS positions using JPL Horizons."""

    def __init__(self, query_factory: Callable[..., object] | None = None) -> None:
        if query_factory is None:
            from astroquery.jplhorizons import Horizons

            query_factory = Horizons
        self._query_factory = query_factory

    def positions(
        self,
        target: CatalogObject,
        times: list[datetime],
        observer_code: str = "500",
    ) -> list[SkyPosition]:
        if not times:
            return []
        # A comet's SBDB SPK ID identifies its family of historical orbit
        # solutions.  Passing it to Horizons can therefore return many
        # apparitions instead of one ephemeris.  The primary designation plus
        # CAP asks Horizons to select the apparition closest to the epochs.
        identifier = target.designation.strip()
        closest_apparition = _is_comet(target)
        epochs = Time(times, scale="utc").jd.tolist()
        positions: list[SkyPosition] = []
        try:
            # Keep Horizons request URLs bounded for long capture sequences.
            for start in range(0, len(epochs), 50):
                query = self._query_factory(
                    id=identifier,
                    id_type="designation",
                    location=observer_code.strip() or "500",
                    epochs=epochs[start : start + 50],
                )
                table = query.ephemerides(
                    extra_precision=True,
                    quantities="1",
                    closest_apparition=closest_apparition,
                )
                positions.extend(
                    SkyPosition(float(row["RA"]), float(row["DEC"]))
                    for row in table
                )
        except Exception as exc:
            raise RuntimeError(f"JPL Horizonsの軌道計算に失敗しました: {exc}") from exc
        if len(positions) != len(times):
            raise RuntimeError(
                "JPL Horizonsから一部の撮影時刻の座標を取得できませんでした。"
            )
        return positions
