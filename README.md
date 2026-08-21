# IONNA Rechargery Tracker

A local, history-aware tracker for the [IONNA Rechargery map](https://www.ionna.com/rechargeries/find-a-rechargery/). It makes one direct HTTP request, extracts the `window.allLocations` JSON embedded in the page, stores current and historical observations in local MongoDB, and serves a Flask dashboard.

The Location Explorer keeps its filter-aware Leaflet map and sortable table synchronized, so both always show the same locations. It uses the coordinates IONNA publishes for each location and loads only the OpenStreetMap tiles needed for the visible viewport, with attribution shown on the map; no geocoding service or API key is required.

The direct request is intentional: browser network inspection showed that IONNA embeds all location data in the page rather than loading it from a separate locations API. Google Maps requests only render the map. An optional Playwright fallback is available if IONNA later changes the page to require rendering.

## What it tracks

- Open, opening-soon, under-renovation, and unknown locations
- State, Rechargery type, address, coordinates, price, speed, connectors, and amenities
- New locations first observed after the initial baseline
- Status changes and observed openings
- Counts at every collection run for trend charts

IONNA does not currently publish an opening date in the map data. The first import is therefore marked as a baseline and is not treated as network growth. A location's `first_observed_open_at` is set only when this tracker actually sees it change from a non-open status to open.

## Setup

Prerequisites: Python 3.11+ and a local MongoDB server listening on `mongodb://127.0.0.1:27017`.

```bash
cd /Users/marcus.salinas/Programming/Personal/ionna-rechargery-tracker
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Run a collection:

```bash
python scrape.py
```

Start the dashboard:

```bash
python server.py
```

Then open <http://127.0.0.1:5050>.

Run the collector whenever you want a fresh observation. There is deliberately no scheduler.

## Optional headless-browser fallback

The normal collector does not launch a browser. To install and enable the fallback:

```bash
pip install -r requirements-browser.txt
playwright install chromium
python scrape.py --browser-fallback
```

The fallback runs only when the direct HTTP fetch or embedded-JSON extraction fails.

## Commands

```bash
# Preview live data without writing to MongoDB
python scrape.py --dry-run

# Print parsed records as JSON
python scrape.py --dry-run --json

# Use a different MongoDB database
MONGODB_DATABASE=my_ionna_data python scrape.py

# Run tests
python -m unittest discover -s tests -v
node --test tests/test_dashboard.js
```

## MongoDB collections

- `locations`: latest known record for each stable IONNA location ID
- `observations`: one compact observation per location per run
- `events`: discoveries and status transitions
- `runs`: run timestamp, method, counts, and content hash

Indexes are created automatically. Location and observation writes use MongoDB bulk operations so repeated runs remain fast.
