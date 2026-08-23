from collections import Counter
from datetime import datetime, timedelta, timezone
import unittest
from uuid import uuid4

from pymongo.errors import PyMongoError

from ionna_tracker.analytics import dashboard_data
from ionna_tracker.config import Settings
from ionna_tracker.parser import normalize_location
from ionna_tracker.storage import connect, ingest


COLLECTIONS = ("locations", "observations", "events", "runs")
SOURCE_URL = "https://example.test/ionna"


class PrefixedDatabase:
    """Isolate integration data in temporary collections within the project DB."""

    def __init__(self, database, prefix):
        self.database = database
        self.prefix = prefix

    def __getattr__(self, name):
        if name not in COLLECTIONS:
            raise AttributeError(name)
        return self.database[f"{self.prefix}_{name}"]

    def drop_collections(self):
        for name in COLLECTIONS:
            self.database.drop_collection(f"{self.prefix}_{name}")


def build_location(source_id, title, state, note="", price_updated=None):
    return normalize_location(
        source_id,
        {
            "title": title,
            "street": "1 Main St",
            "city": "Test City",
            "state": state,
            "postcode": "00000",
            "note": note,
            "price_updated": price_updated,
            "type": "Rechargery Relay",
            "specs": "4 NACS | 4 CCS",
        },
    )


class StorageLifecycleIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        settings = Settings()
        if settings.mongodb_database != "ionna_rechargery_tracker":
            raise unittest.SkipTest("integration test only uses the project-owned database")
        try:
            cls.client, cls.database = connect(
                settings.mongodb_uri, settings.mongodb_database
            )
        except PyMongoError as exc:
            raise unittest.SkipTest(f"local MongoDB unavailable: {exc}") from exc

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "client"):
            cls.client.close()

    def setUp(self):
        self.db = PrefixedDatabase(
            self.database, f"integration_{uuid4().hex}"
        )

    def tearDown(self):
        self.db.drop_collections()

    def test_baseline_then_discovery_opening_and_missing_location(self):
        first_at = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(
            minutes=2
        )
        second_at = first_at + timedelta(minutes=1)
        initial_open = build_location(
            "1", "Initially Open", "TX", price_updated="updated"
        )
        initially_planned = build_location(
            "2", "Planned Site", "TX", note="Opening Soon"
        )

        baseline = ingest(
            self.db,
            [initial_open, initially_planned],
            SOURCE_URL,
            "integration_test",
            fetched_at=first_at,
        )

        self.assertTrue(baseline["baseline"])
        self.assertEqual(baseline["baseline_locations"], 2)
        self.assertEqual(baseline["discovered"], 0)
        self.assertEqual(self.db.events.count_documents({}), 0)

        now_open = build_location("2", "Planned Site", "TX")
        discovered = build_location(
            "3", "New Renovation", "AZ", note="Under Renovation"
        )
        follow_up = ingest(
            self.db,
            [now_open, discovered],
            SOURCE_URL,
            "integration_test",
            fetched_at=second_at,
        )

        self.assertFalse(follow_up["baseline"])
        self.assertEqual(follow_up["discovered"], 1)
        self.assertEqual(follow_up["changed"], 1)
        self.assertEqual(follow_up["observed_openings"], 1)
        self.assertEqual(follow_up["missing"], 1)
        self.assertEqual(
            follow_up["counts"],
            {
                "total": 2,
                "open": 1,
                "coming_soon": 0,
                "under_renovation": 1,
                "unknown": 0,
                "states": 2,
            },
        )

        event_types = Counter(
            event["event_type"] for event in self.db.events.find({})
        )
        self.assertEqual(
            event_types,
            Counter({"discovered": 1, "status_changed": 1, "observed_open": 1}),
        )
        self.assertEqual(follow_up["changes"]["discovered"], [
            {
                "source_id": "3",
                "title": "New Renovation",
                "city": "Test City",
                "state": "AZ",
                "type": "Rechargery Relay",
                "status": "under_renovation",
            }
        ])
        self.assertEqual(
            len(follow_up["changes"]["updated"]),
            1,
        )
        updated_entry = follow_up["changes"]["updated"][0]
        self.assertEqual(updated_entry["source_id"], "2")
        self.assertEqual(updated_entry["status_from"], "coming_soon")
        self.assertEqual(updated_entry["status_to"], "open")
        changed_fields = {item["field"] for item in updated_entry["field_changes"]}
        self.assertIn("note", changed_fields)
        self.assertIn("status", changed_fields)
        self.assertEqual(self.db.runs.count_documents({}), 2)
        self.assertEqual(self.db.observations.count_documents({}), 4)
        self.assertEqual(self.db.locations.count_documents({}), 3)

        missing = self.db.locations.find_one({"source_id": "1"})
        opened = self.db.locations.find_one({"source_id": "2"})
        new_location = self.db.locations.find_one({"source_id": "3"})
        self.assertFalse(missing["active"])
        self.assertEqual(missing["missing_since"], second_at)
        self.assertEqual(opened["status"], "open")
        self.assertEqual(opened["first_observed_open_at"], second_at)
        self.assertFalse(new_location["baseline_first_seen"])

        dashboard = dashboard_data(self.db, recent_days=7)
        self.assertEqual(
            dashboard["summary"],
            {
                "total": 2,
                "states": 2,
                "open": 1,
                "coming_soon": 0,
                "under_renovation": 1,
                "unknown": 0,
                "new_recent": 1,
                "observed_openings": 1,
            },
        )
        self.assertEqual(len(dashboard["history"]), 2)
        self.assertEqual(len(dashboard["recent_changes"]), 4)
        recent_types = Counter(item["event_type"] for item in dashboard["recent_changes"] if "event_type" in item)
        self.assertEqual(
            recent_types,
            Counter({"discovered": 1, "status_changed": 1, "observed_open": 1, "updated": 1}),
        )
        self.assertEqual(dashboard["monthly_openings"][0]["count"], 1)
