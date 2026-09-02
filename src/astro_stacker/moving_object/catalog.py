from __future__ import annotations

import json
import re
from collections.abc import Callable
from urllib.parse import urlencode
from urllib.request import urlopen

from .models import CatalogObject

SBDB_ENDPOINT = "https://ssd-api.jpl.nasa.gov/sbdb.api"


def _kind_from_designation(designation: str) -> str | None:
    value = designation.strip().upper()
    if re.match(r"^(?:\d+P(?:-|$)|[PCDX]/)", value):
        return "c"
    return None


class SmallBodyCatalog:
    """Search comets and asteroids in NASA/JPL's Small-Body Database."""

    def __init__(self, fetch: Callable[[str], bytes] | None = None) -> None:
        self._fetch = fetch or self._fetch_url

    @staticmethod
    def _fetch_url(url: str) -> bytes:
        with urlopen(url, timeout=20) as response:  # noqa: S310 - fixed HTTPS endpoint
            return response.read()

    def search(self, query: str) -> list[CatalogObject]:
        query = query.strip()
        if not query:
            raise ValueError(
                "彗星または小惑星の名称・符号を入力してください。"
            )
        url = f"{SBDB_ENDPOINT}?{urlencode({'sstr': query, 'no-orbit': 1})}"
        try:
            payload = json.loads(self._fetch(url).decode("utf-8"))
        except Exception as exc:
            raise RuntimeError(
                f"JPL小天体カタログに接続できませんでした: {exc}"
            ) from exc

        if payload.get("list"):
            return [
                CatalogObject(
                    designation=str(item["pdes"]),
                    fullname=str(item.get("name") or item["pdes"]),
                    kind=_kind_from_designation(str(item["pdes"])),
                )
                for item in payload["list"]
            ]
        obj = payload.get("object")
        if obj:
            return [
                CatalogObject(
                    designation=str(obj.get("des") or query),
                    fullname=str(obj.get("fullname") or obj.get("shortname") or query),
                    spk_id=str(obj["spkid"]) if obj.get("spkid") else None,
                    kind=str(obj["kind"]) if obj.get("kind") else None,
                )
            ]
        return []
