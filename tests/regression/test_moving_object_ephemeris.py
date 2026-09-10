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


def test_comet_uses_primary_designation_and_closest_apparition() -> None:
    received = {}
    target = CatalogObject(
        designation="10P",
        fullname="10P/Tempel 2",
        spk_id="1000094",
        kind="cn",
    )

    positions = HorizonsEphemeris(_recording_factory(received)).positions(
        target,
        [datetime(2026, 9, 10, tzinfo=UTC)],
    )

    assert positions == [SkyPosition(42.5, -7.25)]
    assert received["id"] == "10P"
    assert received["id_type"] == "designation"
    assert received["ephemerides"]["closest_apparition"] is True


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
    assert received["ephemerides"]["closest_apparition"] is True


def test_asteroid_does_not_request_a_comet_apparition() -> None:
    received = {}
    target = CatalogObject(
        designation="433",
        fullname="433 Eros",
        spk_id="2000433",
        kind="an",
    )

    HorizonsEphemeris(_recording_factory(received)).positions(
        target,
        [datetime(2026, 9, 10, tzinfo=UTC)],
    )

    assert received["id"] == "433"
    assert received["ephemerides"]["closest_apparition"] is False
