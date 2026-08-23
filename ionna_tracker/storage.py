from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pymongo import ASCENDING, DESCENDING, InsertOne, MongoClient, UpdateOne
from pymongo.database import Database

from .parser import payload_hash

TRACKED_FIELDS = (
    "title",
    "street",
    "city",
    "state",
    "postcode",
    "country",
    "note",
    "status",
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
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def connect(uri: str, database_name: str) -> tuple[MongoClient, Database]:
    client = MongoClient(uri, serverSelectionTimeoutMS=5000, tz_aware=True)
    client.admin.command("ping")
    return client, client[database_name]


def ensure_indexes(db: Database) -> None:
    db.locations.create_index("source_id", unique=True)
    db.locations.create_index([("active", ASCENDING), ("state", ASCENDING)])
    db.locations.create_index([("active", ASCENDING), ("status", ASCENDING)])
    db.locations.create_index([("first_seen_at", DESCENDING)])
    db.observations.create_index([("run_id", ASCENDING), ("source_id", ASCENDING)], unique=True)
    db.observations.create_index([("observed_at", DESCENDING)])
    db.events.create_index([("occurred_at", DESCENDING)])
    db.events.create_index([("event_type", ASCENDING), ("occurred_at", DESCENDING)])
    db.runs.create_index("run_id", unique=True)
    db.runs.create_index([("fetched_at", DESCENDING)])


def _counts(locations: list[dict[str, Any]]) -> dict[str, Any]:
    statuses = Counter(item["status"] for item in locations)
    return {
        "total": len(locations),
        "open": statuses.get("open", 0),
        "coming_soon": statuses.get("coming_soon", 0),
        "under_renovation": statuses.get("under_renovation", 0),
        "unknown": statuses.get("unknown", 0),
        "states": len({item["state"] for item in locations if item["state"]}),
    }


def _field_changes(previous: dict[str, Any], location: dict[str, Any]) -> list[dict[str, Any]]:
    changes = []
    for field in TRACKED_FIELDS:
        previous_value = previous.get(field)
        current_value = location.get(field)
        if previous_value != current_value:
            changes.append(
                {
                    "field": field,
                    "from": previous_value,
                    "to": current_value,
                }
            )
    return changes


def _run_changes_for_update(
    location: dict[str, Any],
    previous: dict[str, Any],
    field_changes: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "source_id": location["source_id"],
        "title": location["title"],
        "city": location["city"],
        "state": location["state"],
        "type": location["type"],
        "status_from": previous.get("status"),
        "status_to": location["status"],
        "field_changes": field_changes,
        "change_count": len(field_changes),
    }


def _run_changes_for_discovered(location: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_id": location["source_id"],
        "title": location["title"],
        "city": location["city"],
        "state": location["state"],
        "type": location["type"],
        "status": location["status"],
    }


def _run_changes_for_missing(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_id": doc["source_id"],
        "title": doc["title"],
        "city": doc["city"],
        "state": doc["state"],
        "type": doc["type"],
    }


def ingest(
    db: Database,
    locations: list[dict[str, Any]],
    source_url: str,
    fetch_method: str,
    fetched_at: datetime | None = None,
) -> dict[str, Any]:
    ensure_indexes(db)
    fetched_at = fetched_at or utc_now()
    run_id = str(uuid4())
    source_ids = [item["source_id"] for item in locations]
    existing = {
        item["source_id"]: item
        for item in db.locations.find({"source_id": {"$in": source_ids}})
    }
    baseline = db.runs.count_documents({}) == 0 and db.locations.count_documents({}) == 0

    location_ops = []
    observation_ops = []
    event_ops = []
    discovered_entries = []
    updated_entries = []
    changed = 0
    discovered = 0
    observed_openings = 0

    for location in locations:
        source_id = location["source_id"]
        previous = existing.get(source_id)
        set_fields = {
            **location,
            "last_seen_at": fetched_at,
            "last_seen_run_id": run_id,
            "active": True,
            "missing_since": None,
        }
        set_on_insert = {
            "first_seen_at": fetched_at,
            "first_seen_run_id": run_id,
            "baseline_first_seen": baseline,
        }

        if previous is None:
            discovered += 1
            set_fields["status_changed_at"] = fetched_at
            if not baseline:
                discovered_entries.append(_run_changes_for_discovered(location))
                event_ops.append(
                    InsertOne(
                        {
                            "event_type": "discovered",
                            "source_id": source_id,
                            "title": location["title"],
                            "state": location["state"],
                            "to_status": location["status"],
                            "occurred_at": fetched_at,
                            "run_id": run_id,
                        }
                    )
                )
        else:
            field_changes = _field_changes(previous, location)
            if previous.get("fingerprint") != location["fingerprint"]:
                changed += 1
                if field_changes:
                    updated_entries.append(
                        _run_changes_for_update(location, previous, field_changes)
                    )

            old_status = previous.get("status")
            new_status = location["status"]
            if old_status != new_status:
                set_fields["status_changed_at"] = fetched_at
                event_ops.append(
                    InsertOne(
                        {
                            "event_type": "status_changed",
                            "source_id": source_id,
                            "title": location["title"],
                            "state": location["state"],
                            "from_status": old_status,
                            "to_status": new_status,
                            "occurred_at": fetched_at,
                            "run_id": run_id,
                        }
                    )
                )
                if old_status != "open" and new_status == "open":
                    observed_openings += 1
                    set_fields["first_observed_open_at"] = previous.get(
                        "first_observed_open_at", fetched_at
                    )
                    event_ops.append(
                        InsertOne(
                            {
                                "event_type": "observed_open",
                                "source_id": source_id,
                                "title": location["title"],
                                "state": location["state"],
                                "from_status": old_status,
                                "to_status": new_status,
                                "occurred_at": fetched_at,
                                "run_id": run_id,
                            }
                        )
                    )

        location_ops.append(
            UpdateOne(
                {"source_id": source_id},
                {
                    "$set": set_fields,
                    "$setOnInsert": set_on_insert,
                    "$inc": {"times_seen": 1},
                },
                upsert=True,
            )
        )
        observation_ops.append(
            InsertOne(
                {
                    "run_id": run_id,
                    "observed_at": fetched_at,
                    "source_id": source_id,
                    "fingerprint": location["fingerprint"],
                    "status": location["status"],
                    "state": location["state"],
                    "type": location["type"],
                }
            )
        )

    if location_ops:
        db.locations.bulk_write(location_ops, ordered=False)
    if observation_ops:
        db.observations.bulk_write(observation_ops, ordered=False)
    if event_ops:
        db.events.bulk_write(event_ops, ordered=False)

    missing_result = db.locations.update_many(
        {"source_id": {"$nin": source_ids}, "active": True},
        {
            "$set": {
                "active": False,
                "missing_since": fetched_at,
                "last_missing_run_id": run_id,
            }
        },
    )
    missing_entries = [
        _run_changes_for_missing(item)
        for item in db.locations.find(
            {
                "source_id": {"$nin": source_ids},
                "active": False,
                "last_missing_run_id": run_id,
            },
            {
                "_id": False,
                "source_id": True,
                "title": True,
                "city": True,
                "state": True,
                "type": True,
            },
        )
    ]

    counts = _counts(locations)
    run = {
        "run_id": run_id,
        "fetched_at": fetched_at,
        "source_url": source_url,
        "fetch_method": fetch_method,
        "payload_hash": payload_hash(locations),
        "baseline": baseline,
        "counts": counts,
        "discovered": 0 if baseline else discovered,
        "baseline_locations": discovered if baseline else 0,
        "changed": changed,
        "observed_openings": observed_openings,
        "missing": missing_result.modified_count,
        "changes": {
            "discovered": discovered_entries if not baseline else [],
            "updated": updated_entries,
            "missing": missing_entries,
        },
    }
    db.runs.insert_one(run)
    run.pop("_id", None)
    return run
