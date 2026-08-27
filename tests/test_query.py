import io
import json
import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

from ionna_tracker.parser import normalize_location
from query import (
    build_parser,
    get_latest_run_data,
    get_recent_changes,
    get_runs_history,
    inspect_station,
    list_stations,
    main,
    print_latest_run,
    print_runs_history,
    print_recent_changes,
    print_stations,
    print_station_inspection,
    serialize_for_json,
)


class QueryUnitTests(unittest.TestCase):
    def test_serialize_for_json(self):
        now = datetime(2026, 8, 27, 12, 0, 0, tzinfo=timezone.utc)
        payload = {
            "_id": "should_be_removed",
            "time": now,
            "list": [now, {"_id": "nested_id", "val": 42}],
            "str": "test",
        }
        res = serialize_for_json(payload)
        self.assertNotIn("_id", res)
        self.assertEqual(res["time"], "2026-08-27T12:00:00+00:00")
        self.assertEqual(res["list"][0], "2026-08-27T12:00:00+00:00")
        self.assertNotIn("_id", res["list"][1])
        self.assertEqual(res["list"][1]["val"], 42)

    def test_parser_arguments(self):
        parser = build_parser()
        args = parser.parse_args([])
        self.assertFalse(args.latest)
        self.assertIsNone(args.runs)
        self.assertFalse(args.changes)

        args = parser.parse_args(["--runs", "5"])
        self.assertEqual(args.runs, 5)

        args = parser.parse_args(["--changes", "--days", "14"])
        self.assertTrue(args.changes)
        self.assertEqual(args.days, 14)

        args = parser.parse_args(["--state", "TX", "--status", "open", "--search", "Circle"])
        self.assertEqual(args.state, "TX")
        self.assertEqual(args.status, "open")
        self.assertEqual(args.search, "Circle")

        args = parser.parse_args(["--station", "101", "--json"])
        self.assertEqual(args.station, "101")
        self.assertTrue(args.json)

    def test_print_helpers_execute_without_error(self):
        now = datetime(2026, 8, 27, 8, 0, 0, tzinfo=timezone.utc)
        mock_run_data = {
            "run": {
                "run_id": "run-123",
                "fetched_at": now,
                "fetch_method": "http",
                "baseline": False,
                "discovered": 1,
                "changed": 1,
                "observed_openings": 1,
                "missing": 0,
                "counts": {
                    "total": 10,
                    "open": 8,
                    "coming_soon": 2,
                    "under_renovation": 0,
                    "unknown": 0,
                    "states": 3,
                },
                "changes": {
                    "discovered": [
                        {
                            "source_id": "1",
                            "title": "New Station",
                            "city": "Austin",
                            "state": "TX",
                            "type": "Rechargery Relay",
                            "status": "coming_soon",
                        }
                    ],
                    "updated": [
                        {
                            "source_id": "2",
                            "title": "Updated Station",
                            "status_from": "coming_soon",
                            "status_to": "open",
                            "field_changes": [
                                {"field": "status", "from": "coming_soon", "to": "open"},
                                {"field": "price_per_kwh", "from": 0.35, "to": 0.39},
                            ],
                        },
                        {
                            "source_id": "3",
                            "title": "Image Refreshed Station",
                            "status_from": "open",
                            "status_to": "open",
                            "field_changes": [
                                {
                                    "field": "image_url",
                                    "from": "https://example.com/old.jpg",
                                    "to": "https://example.com/new.jpg",
                                },
                            ],
                        },
                    ],
                    "missing": [],
                },
            },
            "current_network": {
                "total": 10,
                "open": 8,
                "coming_soon": 2,
                "under_renovation": 0,
                "unknown": 0,
                "states": 3,
            },
        }

        # Test output printing
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            print_latest_run(mock_run_data)
            out = mock_out.getvalue()
            self.assertIn("LATEST RUN REPORT", out)
            self.assertIn("New Station", out)
            self.assertIn("Updated Station", out)
            self.assertIn("price_per_kwh: 0.35 -> 0.39", out)
            self.assertIn("IMAGE-ONLY UPDATES", out)
            self.assertIn("Image Refreshed Station", out)

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            print_runs_history([mock_run_data["run"]])
            out = mock_out.getvalue()
            self.assertIn("FETCHED AT", out)
            self.assertIn("2026-08-27", out)

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            mock_events = [
                {
                    "event_type": "discovered",
                    "source_id": "1",
                    "title": "New Station",
                    "state": "TX",
                    "to_status": "coming_soon",
                    "occurred_at": now,
                },
                {
                    "event_type": "observed_open",
                    "source_id": "2",
                    "title": "Opened Station",
                    "state": "TX",
                    "from_status": "coming_soon",
                    "occurred_at": now,
                },
            ]
            print_recent_changes(mock_events, days=7)
            out = mock_out.getvalue()
            self.assertIn("DISCOVERED: [1] New Station", out)
            self.assertIn("OPENING: [2] Opened Station", out)

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            mock_stations = [
                {
                    "source_id": "1",
                    "title": "Sample Station",
                    "city": "Austin",
                    "state": "TX",
                    "status": "open",
                    "nacs_connectors": 4,
                    "ccs_connectors": 4,
                    "speed_kw": 400.0,
                }
            ]
            print_stations(mock_stations, limit=10)
            out = mock_out.getvalue()
            self.assertIn("Sample Station", out)
            self.assertIn("4 NACS / 4 CCS", out)

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            mock_station_detail = {
                "station": {
                    "source_id": "1",
                    "title": "Detailed Station",
                    "status": "open",
                    "note": None,
                    "type": "Rechargery Relay",
                    "street": "123 Main St",
                    "city": "Austin",
                    "state": "TX",
                    "postcode": "78701",
                    "latitude": 30.2,
                    "longitude": -97.7,
                    "speed_kw": 400.0,
                    "nacs_connectors": 4,
                    "ccs_connectors": 4,
                    "price_text": "$0.39/kWh",
                    "price_per_kwh": 0.39,
                    "amenities": ["Restrooms", "Shopping"],
                    "first_seen_at": now,
                    "last_seen_at": now,
                    "first_observed_open_at": now,
                    "link": "https://example.com/station",
                    "image_url": "https://example.com/img.jpg",
                },
                "events": [
                    {
                        "event_type": "discovered",
                        "to_status": "open",
                        "occurred_at": now,
                    }
                ],
            }
            print_station_inspection(mock_station_detail)
            out = mock_out.getvalue()
            self.assertIn("Detailed Station", out)
            self.assertIn("Restrooms, Shopping", out)
            self.assertIn("First discovered with status 'open'", out)


if __name__ == "__main__":
    unittest.main()
