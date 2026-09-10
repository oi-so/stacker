from datetime import UTC, datetime

from astro_stacker.moving_object.ephemeris import HorizonsEphemeris
from astro_stacker.moving_object.models import CatalogObject, SkyPosition


class QueryResult:
    def __init__(self, received: dict):
        self.received = received

    def ephemerides(self, **kwargs):
        self.received["ephemerides"] = kwargs
        return [{"RA": 42.5, "DEC": -7.25}]


def _recording_factory(received: dict):
    def factory(**kwargs):
        received.update(kwargs)
        return QueryResult(received)

    return factory


def test_spk_id_is_sent_as_horizons_designation() -> None:
    received = {}
    target = CatalogObject(
        designation="94P",
        fullname="94P/Russell 4",
        spk_id="1000094",
        kind="cn",
    )

    positions = HorizonsEphemeris(_recording_factory(received)).positions(
        target,
        [datetime(2026, 9, 10, tzinfo=UTC)],
    )

    assert positions == [SkyPosition(42.5, -7.25)]
    assert received["id"] == "1000094"
    assert received["id_type"] == "designation"


def test_primary_designation_uses_same_unambiguous_horizons_syntax() -> None:
    received = {}
    target = CatalogObject(
        designation="C/2025 A1",
        fullname="Example comet",
    )

    HorizonsEphemeris(_recording_factory(received)).positions(
        target,
        [datetime(2026, 9, 10, tzinfo=UTC)],
        observer_code="568",
    )

    assert received["id"] == "C/2025 A1"
    assert received["id_type"] == "designation"
    assert received["location"] == "568"
