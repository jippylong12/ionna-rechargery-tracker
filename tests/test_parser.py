import json
import unittest

from ionna_tracker.parser import (
    LocationParseError,
    classify_status,
    extract_locations,
    normalize_location,
)


class ParserTests(unittest.TestCase):
    def test_extracts_embedded_locations_without_greedy_matching(self):
        payload = {
            "42": {
                "title": "A {brace} in a string",
                "state": "TX",
                "price_updated": "recent",
            }
        }
        html = f"<script>window.allLocations = {json.dumps(payload)}; doOtherThing({{}});</script>"
        self.assertEqual(extract_locations(html), payload)

    def test_missing_assignment_is_an_explicit_parse_error(self):
        with self.assertRaises(LocationParseError):
            extract_locations("<html></html>")

    def test_status_classification(self):
        self.assertEqual(classify_status("Opening Soon", None), "coming_soon")
        self.assertEqual(classify_status("We're Workin' On It...", None), "coming_soon")
        self.assertEqual(classify_status("Under Renovation", None), "under_renovation")
        self.assertEqual(classify_status("", "updated"), "open")
        self.assertEqual(classify_status("", None), "open")

    def test_normalizes_connectors_price_coordinates_and_amenities(self):
        item = normalize_location(
            "101",
            {
                "title": "Example Rechargery Relay",
                "street": "1 Main St",
                "city": "Austin",
                "state": "tx",
                "postcode": "78701",
                "note": "Opening Soon",
                "attributes": {"restrooms": {"name": "Restrooms"}},
                "specs": "<strong>Connectors</strong>4 NACS | 6 CCS",
                "price": "$0.39/kWh Plus Tax",
                "speed": "400",
                "lat": "30.1",
                "lon": "-97.7",
                "type": "Rechargery Relay",
            },
        )
        self.assertEqual(item["status"], "coming_soon")
        self.assertEqual(item["state"], "TX")
        self.assertEqual(item["nacs_connectors"], 4)
        self.assertEqual(item["ccs_connectors"], 6)
        self.assertEqual(item["price_per_kwh"], 0.39)
        self.assertEqual(item["speed_kw"], 400.0)
        self.assertEqual(item["amenities"], ["Restrooms"])
        self.assertEqual(item["latitude"], 30.1)
        self.assertTrue(item["fingerprint"])


if __name__ == "__main__":
    unittest.main()
