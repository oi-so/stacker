from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from astropy.time import Time

from .models import CatalogObject, SkyPosition


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
        identifier = target.spk_id or target.designation
        epochs = Time(times, scale="utc").jd.tolist()
        positions: list[SkyPosition] = []
        try:
            # Keep Horizons request URLs bounded for long capture sequences.
            for start in range(0, len(epochs), 50):
                query = self._query_factory(
                    id=identifier,
                    id_type=None if target.spk_id else "smallbody",
                    location=observer_code.strip() or "500",
                    epochs=epochs[start : start + 50],
                )
                table = query.ephemerides(extra_precision=True, quantities="1")
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
