#!/usr/bin/env python3
"""CLI query tool for inspecting and searching IONNA Rechargery Tracker data.

Provides fast terminal inspection and JSON export across:
- Latest collection run summary and station-by-station diffs.
- Historical collection run logs and growth trends.
- Recent network lifecycle events (discoveries, openings, status transitions).
- Station directory filtering by state, operational status, type, or search term.
- Single-station metadata inspection and historical event timeline.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import sys
from typing import Any

from pymongo.database import Database
from pymongo.errors import PyMongoError, ServerSelectionTimeoutError

from ionna_tracker.config import Settings
from ionna_tracker.storage import connect


def _iso(value: Any) -> str | None:
    """Format a datetime value as an ISO-8601 string."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    return str(value) if value is not None else None


def _format_dt(value: Any) -> str:
    """Format a datetime value into a human-readable UTC timestamp string."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.strftime("%Y-%m-%d %H:%M:%S UTC")
    return str(value) if value is not None else "—"


def _format_val(value: Any) -> str:
    """Format a field diff value cleanly for terminal display."""
    if value is None:
        return "—"
    if isinstance(value, list):
        return ", ".join(map(str, value)) if value else "—"
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def get_latest_run_data(db: Database) -> dict[str, Any] | None:
    """Fetch the latest scrape run metadata and current network count totals.

    Args:
        db: MongoDB database instance.

    Returns:
        Dictionary with 'run' document and 'current_network' totals, or None if no runs exist.
    """
    run = db.runs.find_one({}, sort=[("fetched_at", -1)])
    if not run:
        return None
    run.pop("_id", None)

    active_locations = list(db.locations.find({"active": True}, {"_id": False}))
    statuses = {}
    for loc in active_locations:
        status = loc.get("status", "unknown")
        statuses[status] = statuses.get(status, 0) + 1

    states = {loc.get("state") for loc in active_locations if loc.get("state")}

    return {
        "run": run,
        "current_network": {
            "total": len(active_locations),
            "open": statuses.get("open", 0),
            "coming_soon": statuses.get("coming_soon", 0),
            "under_renovation": statuses.get("under_renovation", 0),
            "unknown": statuses.get("unknown", 0),
            "states": len(states),
        },
    }


def print_latest_run(data: dict[str, Any]) -> None:
    """Print formatted terminal report for the latest scrape run and its deltas."""
    run = data["run"]
    current = data["current_network"]
    fetched_at = run.get("fetched_at")
    baseline = run.get("baseline", False)
    changes = run.get("changes", {})

    print("=" * 64)
    print("  IONNA RECHARGERY TRACKER — LATEST RUN REPORT")
    print("=" * 64)
    print(f"Run Timestamp:    {_format_dt(fetched_at)}")
    print(f"Fetch Method:     {run.get('fetch_method', 'http')}")
    print(f"Run ID:           {run.get('run_id')}")
    print(f"Baseline Run:     {'Yes (initial import)' if baseline else 'No'}")
    print("-" * 64)
    print("CURRENT NETWORK TOTALS:")
    print(
        f"  Total: {current['total']} | Open: {current['open']} | "
        f"Coming Soon: {current['coming_soon']} | "
        f"Under Renovation: {current['under_renovation']} | "
        f"States: {current['states']}"
    )
    print("-" * 64)

    if baseline:
        print(f"Initial baseline recorded {run.get('baseline_locations', 0)} stations.")
        print("=" * 64)
        return

    discovered_count = run.get("discovered", 0)
    changed_count = run.get("changed", 0)
    openings_count = run.get("observed_openings", 0)
    missing_count = run.get("missing", 0)

    print("RUN DELTAS:")
    print(
        f"  Discovered: {discovered_count} | Updated: {changed_count} | "
        f"Observed Openings: {openings_count} | Missing: {missing_count}"
    )
    print("-" * 64)

    discovered_entries = changes.get("discovered", [])
    if discovered_entries:
        print(f"\n[+] NEWLY DISCOVERED STATIONS ({len(discovered_entries)}):")
        for item in discovered_entries:
            title = item.get("title", "Unknown")
            state = item.get("state", "—")
            city = item.get("city", "—")
            stype = item.get("type", "—")
            status = item.get("status", "—")
            source_id = item.get("source_id", "—")
            print(f"  • [{source_id}] {title}")
            print(f"    Location: {city}, {state} | Type: {stype} | Status: {status}")

    updated_entries = changes.get("updated", [])
    if updated_entries:
        operational_updates = []
        image_only_updates = []

        for item in updated_entries:
            field_changes = item.get("field_changes", [])
            non_image_changes = [c for c in field_changes if c.get("field") != "image_url"]
            if non_image_changes:
                operational_updates.append((item, field_changes))
            else:
                image_only_updates.append(item)

        if operational_updates:
            print(f"\n[~] UPDATED STATIONS - OPERATIONAL CHANGES ({len(operational_updates)}):")
            for item, field_changes in operational_updates:
                title = item.get("title", "Unknown")
                source_id = item.get("source_id", "—")
                status_from = item.get("status_from", "—")
                status_to = item.get("status_to", "—")
                status_text = (
                    f" ({status_from} -> {status_to})" if status_from != status_to else ""
                )
                print(f"  • [{source_id}] {title}{status_text}")
                for diff in field_changes:
                    field = diff.get("field")
                    before = _format_val(diff.get("from"))
                    after = _format_val(diff.get("to"))
                    print(f"      - {field}: {before} -> {after}")
        else:
            print("\n[~] No non-image operational changes occurred in this run.")

        if image_only_updates:
            print(f"\n[~] IMAGE-ONLY UPDATES ({len(image_only_updates)}):")
            for item in image_only_updates:
                title = item.get("title", "Unknown")
                source_id = item.get("source_id", "—")
                print(f"  • [{source_id}] {title} (image_url refreshed)")
    else:
        print("\n[~] No station updates in this run.")

    missing_entries = changes.get("missing", [])
    if missing_entries:
        print(f"\n[-] MISSING / REMOVED STATIONS ({len(missing_entries)}):")
        for item in missing_entries:
            title = item.get("title", "Unknown")
            source_id = item.get("source_id", "—")
            print(f"  • [{source_id}] {title} ({item.get('city')}, {item.get('state')})")

    print("\n" + "=" * 64)


def get_runs_history(db: Database, limit: int = 10) -> list[dict[str, Any]]:
    """Retrieve historical collection run documents sorted from most recent."""
    runs = list(db.runs.find({}, {"_id": False}).sort("fetched_at", -1).limit(limit))
    return runs


def print_runs_history(runs: list[dict[str, Any]]) -> None:
    """Render historical collection runs as a formatted ASCII table."""
    if not runs:
        print("No collection runs found.")
        return

    print("=" * 96)
    print(f"{'FETCHED AT (UTC)':<22} | {'TOTAL':<5} | {'OPEN':<5} | {'SOON':<5} | {'RENOV':<5} | {'+DISC':<5} | {'~CHG':<5} | {'*OPEN':<5} | {'-MISS':<5} | {'METHOD':<6}")
    print("=" * 96)
    for r in runs:
        dt_str = _format_dt(r.get("fetched_at"))[:19]
        counts = r.get("counts", {})
        total = counts.get("total", 0)
        open_c = counts.get("open", 0)
        soon_c = counts.get("coming_soon", 0)
        renov_c = counts.get("under_renovation", 0)
        disc = r.get("discovered", 0)
        changed = r.get("changed", 0)
        openings = r.get("observed_openings", 0)
        missing = r.get("missing", 0)
        method = r.get("fetch_method", "http")[:6]

        print(
            f"{dt_str:<22} | {total:<5} | {open_c:<5} | {soon_c:<5} | {renov_c:<5} | "
            f"{disc:<5} | {changed:<5} | {openings:<5} | {missing:<5} | {method:<6}"
        )
    print("=" * 96)


def get_recent_changes(db: Database, days: int = 7) -> list[dict[str, Any]]:
    """Retrieve lifecycle events occurring within the specified lookback days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    events = list(
        db.events.find({"occurred_at": {"$gte": cutoff}}, {"_id": False}).sort(
            "occurred_at", -1
        )
    )
    return events


def print_recent_changes(events: list[dict[str, Any]], days: int) -> None:
    """Print chronological lifecycle events for the recent timeframe."""
    print("=" * 80)
    print(f"  EVENTS & CHANGES IN THE LAST {days} DAYS ({len(events)} Total)")
    print("=" * 80)
    if not events:
        print("No events recorded during this time window.")
        return

    for ev in events:
        event_type = ev.get("event_type", "event").upper()
        dt_str = _format_dt(ev.get("occurred_at"))
        title = ev.get("title", "Unknown")
        state = ev.get("state", "—")
        source_id = ev.get("source_id", "—")

        if event_type == "DISCOVERED":
            to_status = ev.get("to_status", "—")
            print(f"[{dt_str}] [+] DISCOVERED: [{source_id}] {title} ({state}) — Status: {to_status}")
        elif event_type == "OBSERVED_OPEN":
            from_status = ev.get("from_status", "—")
            print(f"[{dt_str}] [*] OPENING: [{source_id}] {title} ({state}) — Opened! (was {from_status})")
        elif event_type == "STATUS_CHANGED":
            from_status = ev.get("from_status", "—")
            to_status = ev.get("to_status", "—")
            print(f"[{dt_str}] [~] STATUS: [{source_id}] {title} ({state}) — {from_status} -> {to_status}")
        else:
            print(f"[{dt_str}] [•] {event_type}: [{source_id}] {title} ({state})")
    print("=" * 80)


def list_stations(
    db: Database,
    state: str | None = None,
    status: str | None = None,
    stype: str | None = None,
    search: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Query active stations matching optional state, status, type, or search filters."""
    query: dict[str, Any] = {"active": True}
    if state:
        query["state"] = {"$regex": f"^{state.strip()}$", "$options": "i"}
    if status:
        query["status"] = status.strip().lower()
    if stype:
        query["type"] = {"$regex": stype.strip(), "$options": "i"}
    if search:
        query["$or"] = [
            {"title": {"$regex": search, "$options": "i"}},
            {"city": {"$regex": search, "$options": "i"}},
            {"street": {"$regex": search, "$options": "i"}},
            {"note": {"$regex": search, "$options": "i"}},
        ]

    stations = list(
        db.locations.find(query, {"_id": False}).sort([("state", 1), ("city", 1)]).limit(limit)
    )
    return stations


def print_stations(stations: list[dict[str, Any]], limit: int) -> None:
    """Render matching stations in an ASCII table."""
    if not stations:
        print("No matching stations found.")
        return

    print("=" * 110)
    print(f"{'ID':<6} | {'STATE':<5} | {'CITY':<16} | {'STATUS':<14} | {'PLUGS (NACS/CCS)':<16} | {'SPEED':<7} | {'TITLE'}")
    print("=" * 110)
    for s in stations:
        sid = str(s.get("source_id", "—"))[:6]
        state = str(s.get("state", "—"))[:5]
        city = str(s.get("city", "—"))[:16]
        status = str(s.get("status", "—"))[:14]
        nacs = s.get("nacs_connectors") or 0
        ccs = s.get("ccs_connectors") or 0
        plugs = f"{nacs} NACS / {ccs} CCS"
        speed = f"{int(s.get('speed_kw', 0))}kW" if s.get("speed_kw") else "—"
        title = str(s.get("title", "—"))

        print(f"{sid:<6} | {state:<5} | {city:<16} | {status:<14} | {plugs:<16} | {speed:<7} | {title}")
    print("=" * 110)
    print(f"Showing {len(stations)} stations.")


def inspect_station(db: Database, query_term: str) -> dict[str, Any] | None:
    """Find a station by source ID or title and retrieve its complete event history."""
    doc = db.locations.find_one({"source_id": query_term}, {"_id": False})
    if not doc:
        doc = db.locations.find_one(
            {"title": {"$regex": query_term, "$options": "i"}}, {"_id": False}
        )
    if not doc:
        return None

    events = list(
        db.events.find({"source_id": doc.get("source_id")}, {"_id": False}).sort(
            "occurred_at", 1
        )
    )
    return {"station": doc, "events": events}


def print_station_inspection(data: dict[str, Any]) -> None:
    """Print comprehensive details and event history for a single station."""
    s = data["station"]
    events = data.get("events", [])

    print("=" * 70)
    print(f"  STATION DETAILS: {s.get('title', 'Unknown')}")
    print("=" * 70)
    print(f"Source ID:        {s.get('source_id')}")
    print(f"Status:           {s.get('status')} (Note: {s.get('note') or 'None'})")
    print(f"Type:             {s.get('type')}")
    print(f"Address:          {s.get('street')}, {s.get('city')}, {s.get('state')} {s.get('postcode')}")
    print(f"Coordinates:      {s.get('latitude')}, {s.get('longitude')}")
    print(f"Speed:            {s.get('speed_kw')} kW")
    print(f"Connectors:       {s.get('nacs_connectors')} NACS / {s.get('ccs_connectors')} CCS")
    print(f"Price:            {s.get('price_text') or '—'} ({s.get('price_per_kwh')} $/kWh)")
    print(f"Amenities:        {', '.join(s.get('amenities', [])) if s.get('amenities') else 'None'}")
    print(f"First Seen:       {_format_dt(s.get('first_seen_at'))}")
    print(f"Last Seen:        {_format_dt(s.get('last_seen_at'))}")
    print(f"First Open At:    {_format_dt(s.get('first_observed_open_at'))}")
    print(f"Source URL:       {s.get('link') or '—'}")
    print(f"Image URL:        {s.get('image_url') or '—'}")
    print("-" * 70)
    print(f"EVENT HISTORY ({len(events)} events):")
    if not events:
        print("  No discrete lifecycle events logged (was part of baseline).")
    else:
        for ev in events:
            dt = _format_dt(ev.get("occurred_at"))
            etype = ev.get("event_type")
            if etype == "discovered":
                print(f"  • {dt}: First discovered with status '{ev.get('to_status')}'")
            elif etype == "observed_open":
                print(f"  • {dt}: Observed opening! (from '{ev.get('from_status')}')")
            elif etype == "status_changed":
                print(f"  • {dt}: Status changed from '{ev.get('from_status')}' to '{ev.get('to_status')}'")
            else:
                print(f"  • {dt}: Event '{etype}'")
    print("=" * 70)


def build_parser() -> argparse.ArgumentParser:
    """Build and configure the argument parser for the query CLI."""
    parser = argparse.ArgumentParser(
        description="Query IONNA Rechargery Tracker data from MongoDB"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--latest",
        action="store_true",
        help="Show summary and detailed deltas from the latest scrape run (default)",
    )
    group.add_argument(
        "--runs",
        "--history",
        type=int,
        nargs="?",
        const=10,
        metavar="N",
        help="List the last N collection runs (default: 10)",
    )
    group.add_argument(
        "--changes",
        action="store_true",
        help="Show network events and changes over recent days (use --days to change timeframe)",
    )
    group.add_argument(
        "--stations",
        action="store_true",
        help="List active stations (supports --state, --status, --type, --search)",
    )
    group.add_argument(
        "--station",
        type=str,
        metavar="ID_OR_NAME",
        help="Inspect full details and history for a specific station ID or title",
    )

    # Timeframe and station filters
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Number of days to inspect when querying changes (default: 7)",
    )
    parser.add_argument("--state", type=str, help="Filter stations by state code (e.g. TX, CA)")
    parser.add_argument(
        "--status",
        type=str,
        help="Filter stations by status (open, coming_soon, under_renovation)",
    )
    parser.add_argument("--type", type=str, dest="stype", help="Filter stations by type")
    parser.add_argument("--search", type=str, help="Search stations by name, city, address, note")
    parser.add_argument(
        "--limit", type=int, default=200, help="Maximum number of items to return"
    )
    parser.add_argument(
        "--json", action="store_true", help="Output results in JSON format"
    )
    return parser


def serialize_for_json(obj: Any) -> Any:
    """Recursively convert datetime objects and MongoDB keys for JSON output."""
    if isinstance(obj, datetime):
        return _iso(obj)
    if isinstance(obj, list):
        return [serialize_for_json(item) for item in obj]
    if isinstance(obj, dict):
        return {key: serialize_for_json(val) for key, val in obj.items() if key != "_id"}
    return obj


def main(argv: list[str] | None = None) -> int:
    """Execute the query CLI command."""
    parser = build_parser()
    args = parser.parse_args(argv)
    settings = Settings()

    try:
        client, db = connect(settings.mongodb_uri, settings.mongodb_database)
    except (ServerSelectionTimeoutError, PyMongoError) as exc:
        print(
            f"Error: Could not connect to MongoDB at {settings.mongodb_uri}\n"
            f"Details: {exc}\n\n"
            "Please ensure MongoDB is running. Options:\n"
            "  • macOS (Homebrew): brew services start mongodb-community\n"
            "  • Docker:           docker run -d -p 27017:27017 --name mongo-ionna mongo:latest\n",
            file=sys.stderr,
        )
        return 1

    try:
        if args.runs is not None:
            runs = get_runs_history(db, limit=args.runs)
            if args.json:
                print(json.dumps(serialize_for_json(runs), indent=2))
            else:
                print_runs_history(runs)
        elif args.changes:
            events = get_recent_changes(db, days=args.days)
            if args.json:
                print(json.dumps(serialize_for_json(events), indent=2))
            else:
                print_recent_changes(events, days=args.days)
        elif args.stations or args.state or args.status or args.stype or args.search:
            stations = list_stations(
                db,
                state=args.state,
                status=args.status,
                stype=args.stype,
                search=args.search,
                limit=args.limit,
            )
            if args.json:
                print(json.dumps(serialize_for_json(stations), indent=2))
            else:
                print_stations(stations, limit=args.limit)
        elif args.station:
            inspection = inspect_station(db, args.station)
            if not inspection:
                print(f"Station '{args.station}' not found.", file=sys.stderr)
                return 1
            if args.json:
                print(json.dumps(serialize_for_json(inspection), indent=2))
            else:
                print_station_inspection(inspection)
        else:
            latest_data = get_latest_run_data(db)
            if not latest_data:
                print("No runs recorded in database yet. Run 'python scrape.py' first.")
                return 0
            if args.json:
                print(json.dumps(serialize_for_json(latest_data), indent=2))
            else:
                print_latest_run(latest_data)
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    sys.exit(main())
