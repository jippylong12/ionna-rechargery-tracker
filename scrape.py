#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys

from ionna_tracker.config import Settings
from ionna_tracker.fetcher import fetch_direct, fetch_with_browser
from ionna_tracker.parser import LocationParseError, extract_locations, normalize_locations
from ionna_tracker.storage import connect, ingest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect IONNA Rechargery locations")
    parser.add_argument(
        "--browser-fallback",
        action="store_true",
        help="Use headless Chromium only if the direct HTTP path fails",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and parse without writing to MongoDB",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print parsed locations as JSON (most useful with --dry-run)",
    )
    return parser.parse_args()


def collect(url: str, browser_fallback: bool):
    try:
        result = fetch_direct(url)
        locations = normalize_locations(extract_locations(result.html))
        return locations, result.method
    except (LocationParseError, OSError, RuntimeError) as direct_error:
        if not browser_fallback:
            raise direct_error
        result = fetch_with_browser(url)
        locations = normalize_locations(extract_locations(result.html))
        return locations, result.method


def main() -> int:
    args = parse_args()
    settings = Settings()
    try:
        locations, method = collect(settings.source_url, args.browser_fallback)
        if args.json:
            print(json.dumps(locations, indent=2, sort_keys=True))
        if args.dry_run:
            print(f"Parsed {len(locations)} locations via {method}; MongoDB unchanged.")
            return 0

        client, db = connect(settings.mongodb_uri, settings.mongodb_database)
        try:
            run = ingest(db, locations, settings.source_url, method)
        finally:
            client.close()

        counts = run["counts"]
        print(
            f"Saved {counts['total']} locations via {method}: "
            f"{counts['open']} open, {counts['coming_soon']} coming soon, "
            f"{counts['under_renovation']} under renovation, "
            f"{counts['unknown']} unknown, {counts['states']} states."
        )
        if run["baseline"]:
            print("Created the initial baseline; it is excluded from growth metrics.")
        else:
            print(
                f"Run changes: {run['discovered']} new, {run['changed']} updated, "
                f"{run['observed_openings']} observed openings, {run['missing']} missing."
            )
        return 0
    except Exception as exc:
        print(f"Collection failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
