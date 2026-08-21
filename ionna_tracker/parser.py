from __future__ import annotations

import hashlib
import json
import re
from typing import Any


ASSIGNMENT_RE = re.compile(r"window\.allLocations\s*=\s*")
CONNECTOR_RE = re.compile(r"(\d+)\s*(NACS|CCS)", re.IGNORECASE)
PRICE_RE = re.compile(r"\$([0-9]+(?:\.[0-9]+)?)\s*/\s*kWh", re.IGNORECASE)


class LocationParseError(ValueError):
    """Raised when the embedded IONNA location payload cannot be parsed."""


def extract_locations(html: str) -> dict[str, dict[str, Any]]:
    """Extract the JSON object assigned to window.allLocations.

    JSONDecoder.raw_decode is used instead of a greedy regular expression, so
    braces inside strings or future JavaScript that follows the object do not
    corrupt extraction.
    """
    match = ASSIGNMENT_RE.search(html)
    if not match:
        raise LocationParseError("window.allLocations was not found in the page")

    payload = html[match.end() :].lstrip()
    try:
        value, _ = json.JSONDecoder().raw_decode(payload)
    except json.JSONDecodeError as exc:
        raise LocationParseError(f"invalid embedded locations JSON: {exc}") from exc

    if not isinstance(value, dict) or not value:
        raise LocationParseError("embedded locations payload was empty or not an object")
    return value


def classify_status(note: str | None, price_updated: Any) -> str:
    normalized = (note or "").strip().lower()
    if "opening soon" in normalized or "workin' on it" in normalized:
        return "coming_soon"
    if "renovation" in normalized:
        return "under_renovation"
    if price_updated:
        return "open"
    if not normalized:
        # IONNA marks non-open sites explicitly in `note`. A small number of
        # live sites omit the transient price-updated string, so note absence is
        # the stable open signal.
        return "open"
    return "unknown"


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _amenities(value: Any) -> list[str]:
    if isinstance(value, dict):
        names = [
            item.get("name", key) if isinstance(item, dict) else str(item)
            for key, item in value.items()
        ]
    elif isinstance(value, list):
        names = [
            item.get("name", "") if isinstance(item, dict) else str(item)
            for item in value
        ]
    else:
        names = []
    return sorted({name.strip() for name in names if name and name.strip()})


def normalize_location(source_id: str, raw: dict[str, Any]) -> dict[str, Any]:
    specs = str(raw.get("specs") or "")
    connector_counts = {
        kind.upper(): int(count) for count, kind in CONNECTOR_RE.findall(specs)
    }
    price_text = str(raw.get("price") or "").strip() or None
    price_match = PRICE_RE.search(price_text or "")
    note = str(raw.get("note") or "").strip()

    location = {
        "source_id": str(source_id),
        "title": str(raw.get("title") or "").strip(),
        "street": str(raw.get("street") or "").strip(),
        "city": str(raw.get("city") or "").strip(),
        "state": str(raw.get("state") or "").strip().upper(),
        "postcode": str(raw.get("postcode") or "").strip(),
        "country": str(raw.get("country") or "").strip(),
        "note": note or None,
        "status": classify_status(note, raw.get("price_updated")),
        "type": str(raw.get("type") or "Unknown").strip(),
        "speed_kw": _as_float(raw.get("speed")),
        "price_text": price_text,
        "price_per_kwh": float(price_match.group(1)) if price_match else None,
        "nacs_connectors": connector_counts.get("NACS"),
        "ccs_connectors": connector_counts.get("CCS"),
        "amenities": _amenities(raw.get("attributes")),
        "latitude": _as_float(raw.get("lat")),
        "longitude": _as_float(raw.get("lon")),
        "link": str(raw.get("link") or "").strip(),
        "image_url": str(raw.get("image") or "").strip(),
    }
    location["fingerprint"] = fingerprint(location)
    return location


def normalize_locations(payload: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    locations = [normalize_location(source_id, raw) for source_id, raw in payload.items()]
    return sorted(locations, key=lambda item: (item["state"], item["city"], item["source_id"]))


def fingerprint(location: dict[str, Any]) -> str:
    tracked = {key: value for key, value in location.items() if key != "fingerprint"}
    encoded = json.dumps(tracked, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def payload_hash(locations: list[dict[str, Any]]) -> str:
    compact = [(item["source_id"], item["fingerprint"]) for item in locations]
    return hashlib.sha256(
        json.dumps(compact, separators=(",", ":")).encode()
    ).hexdigest()
