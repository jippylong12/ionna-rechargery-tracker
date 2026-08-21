from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from pymongo.database import Database


STATUS_ORDER = ["open", "coming_soon", "under_renovation", "unknown"]


def _iso(value: Any) -> str | None:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat().replace("+00:00", "Z")
    return None


def _location_json(item: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "source_id",
        "title",
        "street",
        "city",
        "state",
        "postcode",
        "status",
        "note",
        "type",
        "speed_kw",
        "price_text",
        "price_per_kwh",
        "nacs_connectors",
        "ccs_connectors",
        "amenities",
        "latitude",
        "longitude",
        "link",
        "image_url",
        "baseline_first_seen",
    )
    result = {key: item.get(key) for key in keys}
    result.update(
        first_seen_at=_iso(item.get("first_seen_at")),
        last_seen_at=_iso(item.get("last_seen_at")),
        first_observed_open_at=_iso(item.get("first_observed_open_at")),
    )
    return result


def dashboard_data(db: Database, recent_days: int = 7) -> dict[str, Any]:
    locations = list(db.locations.find({"active": True}, {"_id": False}))
    runs = list(db.runs.find({}, {"_id": False}).sort("fetched_at", 1).limit(500))
    latest_run = runs[-1] if runs else None
    cutoff = datetime.now(timezone.utc) - timedelta(days=recent_days)

    status_counts = Counter(item.get("status", "unknown") for item in locations)
    state_rows: dict[str, Counter] = defaultdict(Counter)
    type_rows: dict[str, Counter] = defaultdict(Counter)
    for item in locations:
        status = item.get("status", "unknown")
        state_rows[item.get("state") or "Unknown"][status] += 1
        type_rows[item.get("type") or "Unknown"][status] += 1

    def rows(source: dict[str, Counter], label_key: str) -> list[dict[str, Any]]:
        result = []
        for label, counts in source.items():
            row = {label_key: label, "total": sum(counts.values())}
            row.update({status: counts.get(status, 0) for status in STATUS_ORDER})
            result.append(row)
        return sorted(result, key=lambda row: (-row["total"], row[label_key]))

    recent_events = list(
        db.events.find({"occurred_at": {"$gte": cutoff}}, {"_id": False})
        .sort("occurred_at", -1)
        .limit(100)
    )
    all_open_events = list(
        db.events.find({"event_type": "observed_open"}, {"_id": False}).sort(
            "occurred_at", 1
        )
    )
    monthly = Counter(
        event["occurred_at"].strftime("%Y-%m")
        for event in all_open_events
        if isinstance(event.get("occurred_at"), datetime)
    )

    history = []
    for run in runs:
        counts = run.get("counts", {})
        history.append(
            {
                "at": _iso(run.get("fetched_at")),
                "total": counts.get("total", 0),
                "open": counts.get("open", 0),
                "coming_soon": counts.get("coming_soon", 0),
                "under_renovation": counts.get("under_renovation", 0),
                "unknown": counts.get("unknown", 0),
                "baseline": bool(run.get("baseline")),
                "discovered": run.get("discovered", 0),
                "observed_openings": run.get("observed_openings", 0),
            }
        )

    recent_new = [event for event in recent_events if event.get("event_type") == "discovered"]
    recent_changes = [
        {
            **{key: value for key, value in event.items() if key != "occurred_at"},
            "occurred_at": _iso(event.get("occurred_at")),
        }
        for event in recent_events
    ]

    return {
        "generated_at": _iso(datetime.now(timezone.utc)),
        "recent_days": recent_days,
        "has_data": bool(latest_run),
        "last_run": (
            {
                **latest_run,
                "fetched_at": _iso(latest_run.get("fetched_at")),
            }
            if latest_run
            else None
        ),
        "summary": {
            "total": len(locations),
            "states": len(state_rows),
            **{status: status_counts.get(status, 0) for status in STATUS_ORDER},
            "new_recent": len(recent_new),
            "observed_openings": len(all_open_events),
        },
        "states": rows(state_rows, "state"),
        "types": rows(type_rows, "type"),
        "history": history,
        "monthly_openings": [
            {"month": month, "count": count} for month, count in sorted(monthly.items())
        ],
        "recent_changes": recent_changes,
        "locations": [_location_json(item) for item in locations],
    }
