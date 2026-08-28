# IONNA Rechargery Tracker

A local, history-aware tracker, CLI query tool, and web dashboard for the [IONNA Rechargery network](https://www.ionna.com/rechargeries/find-a-rechargery/).

It extracts the `window.allLocations` JSON payload embedded in IONNA's public map, stores observations in local MongoDB, and tracks station lifecycle changes over time (new discoveries, status changes, observed openings, price updates, connector modifications).

---

## Quick Start

Get up and running in under a minute:

```bash
# 1. Start MongoDB (if not already running)
# macOS:
brew services start mongodb-community
# or Docker:
docker run -d -p 27017:27017 --name mongo-ionna mongo:latest

# 2. Clone repository & install dependencies
git clone https://github.com/jippylong12/ionna-rechargery-tracker.git
cd ionna-rechargery-tracker
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env

# 3. Scrape initial data
python scrape.py

# 4. Start the web dashboard
python server.py
```

Open **<http://127.0.0.1:5050>** to view the interactive map and table.

---

## Querying the Data

You can inspect and query the dataset via the CLI tool, an AI coding assistant, or the web dashboard.

### 1. CLI Query Tool (`query.py`)

Run `query.py` to inspect the latest scrape run, search stations, or view historical changes:

```bash
# View summary and station diffs from the latest run (default)
python query.py

# View history of the last 10 collection runs
python query.py --runs 10

# View all station events and changes over the last 7 days
python query.py --changes --days 7

# Search and filter active stations
python query.py --state TX
python query.py --status open --state CA
python query.py --search "Circle K"
python query.py --search "Relay" --limit 50

# Inspect a single station's full details and lifecycle event timeline
python query.py --station 6330
python query.py --station "Austin, TX"

# Output any query in JSON format
python query.py --latest --json
python query.py --state TX --json
```

---

### 2. Querying with AI Assistants (`AGENTS.md`)

This repository is configured for AI assistants (Google Antigravity, Cursor, Claude Code, GitHub Copilot) to inspect the MongoDB database and answer questions about network changes.

The included `AGENTS.md` file instructs your AI assistant how to query the database and format operational change reports with before/after field comparisons.

#### Example prompts to ask your AI:
- *"Give me an operational tracker update on the latest run."*
- *"What changed in the IONNA network today?"*
- *"List all newly discovered stations in Texas and Colorado."*
- *"Show me all stations that opened in the past 30 days."*
- *"Did any stations change prices or connector counts recently?"*

---

### 3. Web Dashboard

Run `python server.py` and open <http://127.0.0.1:5050> for:
- **Synchronized Map & Table**: OpenStreetMap-powered Leaflet map and responsive table.
- **Visual Status & Type**: Color coding by operational status (Green: Open, Orange: Coming Soon, Red: Under Renovation) and distinct marker shapes for station types.
- **Search & Sort**: Filter by state, status, or keyword; sort by any column.

---

## Automated Scheduling

Keep your local database updated with scheduled scrapes.

### Option A: macOS LaunchAgent

A built-in management script is provided under `bin/nightly-schedule`. It dynamically configures a launchd agent to run daily at 3:00 AM local time (wakes machine if asleep):

```bash
# Turn on nightly collection at 3:00 AM
bin/nightly-schedule on

# Check schedule status
bin/nightly-schedule status

# Trigger a collection run immediately
bin/nightly-schedule run

# View recent log output
bin/nightly-schedule logs

# Turn off the schedule
bin/nightly-schedule off
```

---

### Option B: Linux / macOS Cron

Add an entry to your crontab (`crontab -e`):

```cron
0 3 * * * cd /path/to/ionna-rechargery-tracker && .venv/bin/python scrape.py >> logs/nightly.log 2>&1
```

---

### Option C: AI Agent Scheduler (Antigravity)

When using Google Antigravity, you can use the `/schedule` slash command to run automated collections in the background:

```text
/schedule CronExpression="0 3 * * *" Prompt="Run python scrape.py and summarize any new station discoveries, openings, or price changes."
```

---

## What It Tracks

- **Operational Status**: Open, Coming Soon, Under Renovation, Unknown.
- **Station Data**: Title, street address, city, state, postal code, GPS coordinates, source link, image URL.
- **Hardware & Pricing**: Max speed (kW), NACS connectors, CCS connectors, price text, normalized price per kWh.
- **Amenities**: Restrooms, dining, shopping, convenience markets, hotels.
- **Lifecycle Events**: First observed date, last seen date, opening date (recorded when a location transitions to open), and field modification diffs.

---

## Optional Headless Browser Fallback

`scrape.py` uses direct HTTP extraction by default without browser overhead. To install and enable the optional Playwright fallback (only invoked if direct extraction fails):

```bash
pip install -r requirements-browser.txt
playwright install chromium

# Run scraper with browser fallback enabled
python scrape.py --browser-fallback
```

---

## Running Tests

```bash
# Python unit and storage integration tests
python -m unittest discover -s tests -v

# JavaScript dashboard frontend tests
node --test tests/test_dashboard.js
```

---

## Database Schema

The tracker manages four collections in MongoDB:

| Collection | Purpose |
| :--- | :--- |
| `locations` | Latest known state for each unique station ID (`source_id`). |
| `observations` | Point-in-time snapshot for each location per collection run. |
| `events` | Discrete lifecycle events (`discovered`, `status_changed`, `observed_open`). |
| `runs` | Collection run metadata: timestamp, method, counts, baseline flag, and delta diffs. |

---

## License

MIT License. See [LICENSE](LICENSE) for details.
