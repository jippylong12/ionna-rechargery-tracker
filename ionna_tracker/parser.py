"""Parsing and normalization routines for IONNA Rechargery data.

Handles:
- Extracting raw JSON embedded in the webpage (`window.allLocations = {...}`).
- Classifying operational status ('open', 'coming_soon', 'under_renovation').
- Parsing connector specs (NACS vs CCS counts) and pricing information.
- Computing deterministic SHA-256 fingerprints for diff detection.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

# Regex to locate the start of the embedded JavaScript object
ASSIGNMENT_RE = re.compile(r"window\.allLocations\s*=\s*")

# Regex to parse connector counts from specs strings like "4 NACS | 6 CCS"
CONNECTOR_RE = re.compile(r"(\d+)\s*(NACS|CCS)", re.IGNORECASE)

# Regex to extract price per kWh (e.g. "$0.39/kWh")
PRICE_RE = re.compile(r"\$([0-9]+(?:\.[0-9]+)?)\s*/\s*kWh", re.IGNORECASE)


class LocationParseError(ValueError):
    """Raised when the embedded IONNA location payload cannot be parsed."""


def extract_locations(html: str) -> dict[str, dict[str, Any]]:
    """Extract the JSON object assigned to `window.allLocations`.

    Uses `json.JSONDecoder().raw_decode` starting at the match index rather than
    greedy regex, ensuring that nested braces inside strings or subsequent JS
    statements do not break extraction.

    Args:
        html: Raw HTML content of the IONNA map page.

    Returns:
        Dictionary mapping station string IDs to raw station attribute dictionaries.

    Raises:
        LocationParseError: If `window.allLocations` is missing, malformed, or empty.
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
    """Classify the station's operational status based on notes and pricing metadata.

    Classification heuristics:
    - 'coming_soon': Contains phrases like 'Opening Soon' or "Workin' On It".
    - 'under_renovation': Contains 'Renovation'.
    - 'open': Explicit price update timestamp or absence of planned/renovation note.

    Args:
        note: Status note string from IONNA payload.
        price_updated: Timestamp or indicator of recent pricing update.

    Returns:
        One of: 'open', 'coming_soon', 'under_renovation', or 'unknown'.
    """
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
    """Safely convert a value to a float or return None."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _amenities(value: Any) -> list[str]:
    """Extract and sort unique amenity names from raw attributes object or list."""
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
    """Normalize a raw IONNA station record into a clean, typed dictionary.

    Extracts numerical connectors, pricing per kWh, cleans address components,
    and attaches a SHA-256 fingerprint for change detection.

    Args:
        source_id: Station unique identifier string.
        raw: Raw station dictionary from `window.allLocations`.

    Returns:
        Normalized station dictionary.
    """
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
    """Normalize a full payload of raw station records and sort deterministically.

    Args:
        payload: Dict of raw station records keyed by source ID.

    Returns:
        List of normalized station records sorted by (state, city, source_id).
    """
    locations = [normalize_location(source_id, raw) for source_id, raw in payload.items()]
    return sorted(locations, key=lambda item: (item["state"], item["city"], item["source_id"]))


def fingerprint(location: dict[str, Any]) -> str:
    """Compute a deterministic SHA-256 hash representing a station's current data.

    Excludes volatile fields such as the fingerprint itself and timestamps.
    """
    tracked = {key: value for key, value in location.items() if key != "fingerprint"}
    encoded = json.dumps(tracked, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def payload_hash(locations: list[dict[str, Any]]) -> str:
    """Compute a deterministic SHA-256 hash representing the entire scrape payload.

    Allows fast comparison of complete run outputs.
    """
    compact = [(item["source_id"], item["fingerprint"]) for item in locations]
    return hashlib.sha256(
        json.dumps(compact, separators=(",", ":")).encode()
    ).hexdigest()
