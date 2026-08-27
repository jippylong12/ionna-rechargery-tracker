# IONNA Rechargery Tracker

A local, history-aware tracker, CLI query engine, and interactive web dashboard for the [IONNA Rechargery network](https://www.ionna.com/rechargeries/find-a-rechargery/).

It extracts the `window.allLocations` JSON payload embedded in IONNA's public map, stores snapshot observations in MongoDB, tracks station lifecycle events (discoveries, openings, price/connector updates, status transitions), and provides multiple ways to explore the data — via web dashboard, command-line queries, or conversational AI assistants.

---

## Features

- **⚡ Fast & Lightweight**: Direct HTTP fetch extracts embedded JSON in milliseconds without launching a browser. *(Playwright fallback available if needed).*
- **🗄️ Historical Tracking**: Distinguishes the initial baseline from actual network growth. Records state transitions, observed openings, price updates, connector modifications, and missing stations.
- **🗺️ Interactive Web Dashboard**: Filter-aware Leaflet map synchronized with a sortable data table. Distinct marker colors indicate operational status, while marker shapes represent Rechargery types. Uses local OpenStreetMap tiles (no geocoding API keys required).
- **💻 CLI Query Engine (`query.py`)**: Instant terminal access to latest run diffs, historical trends, station filtering, and single-station lifecycle inspection with table or JSON output.
- **🤖 AI-Assisted Investigation (`AGENTS.md`)**: Configured for AI assistants (Google Antigravity, Cursor, Claude Code, Copilot, etc.) to investigate MongoDB and generate field-by-field operational change reports.
- **⏰ Flexible Scheduling**: Run nightly via macOS LaunchAgent, standard cron, or an AI background agent.

---

## What It Tracks

- **Status**: Open, Coming Soon, Under Renovation, Unknown.
- **Station Details**: Title, street address, city, state, postal code, GPS coordinates, source URL, image URL.
- **Hardware & Pricing**: Max speed (kW), NACS connectors, CCS connectors, price text, and normalized price per kWh.
- **Amenities**: Restrooms, dining, shopping, convenience markets, hotels.
- **Lifecycle Events**: First observed date, last seen date, opening date (tracked only when a location actually transitions to open), and field-level modification history.

---

## Prerequisites

- **Python 3.11+**
- **MongoDB** running locally or remotely (default: `mongodb://127.0.0.1:27017`)
- *(Optional)* **Node.js 18+** (only needed for frontend test execution)

### Quick MongoDB Setup

<details>
<summary><b>macOS (Homebrew)</b></summary>

```bash
brew tap mongodb/brew
brew install mongodb-community
brew services start mongodb-community
```
</details>

<details>
<summary><b>Docker (macOS / Linux / Windows)</b></summary>

```bash
docker run -d -p 27017:27017 --name mongo-ionna mongo:latest
```
</details>

---

## Quick Start

```bash
# 1. Clone the repository
git clone https://github.com/jippylong12/ionna-rechargery-tracker.git
cd ionna-rechargery-tracker

# 2. Set up virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment (optional overrides)
cp .env.example .env

# 5. Run your first collection (establishes baseline)
python scrape.py

# 6. Start the web dashboard
python server.py
```

Then open your browser at **<http://127.0.0.1:5050>**.

---

## Querying Tracker Data

You can query and inspect the dataset in three ways: **CLI**, **Web Dashboard**, or **AI Assistant**.

### 1. CLI Query Engine (`query.py`)

The included `query.py` tool provides formatted terminal tables and raw JSON feeds:

```bash
# View summary and deltas from the latest collection run (default)
python query.py

# View historical collection runs (last 10 runs)
python query.py --runs 10

# View all network events & status changes over recent days
python query.py --changes --days 7

# Search and filter active stations by state, status, or keyword
python query.py --state TX
python query.py --status open --state CA
python query.py --search "Circle K"
python query.py --search "Relay" --limit 50

# Inspect a single station's full details and historical lifecycle timeline
python query.py --station 6330
python query.py --station "Austin, TX"

# Output any query as JSON (great for scripts or piping to jq)
python query.py --latest --json
python query.py --state TX --json
```

---

### 2. Interactive Web Dashboard

Start the server:
```bash
python server.py
```
Open **<http://127.0.0.1:5050>** to access:
- **Map & Table View**: Live synchronized Leaflet map and responsive table.
- **Status Indicators**: Green (Open), Orange (Coming Soon), Red (Under Renovation).
- **Type Markers**: Circle (`Rechargery @`), Square (`Rechargery Relay`), Star (`Rechargery Lounge / Flagship`).
- **Real-time Filtering**: Filter by state, type, or search term; sort by any column.

---

### 3. AI Assistant Investigation (`AGENTS.md`)

This repository is optimized for pair-programming and investigation with AI coding agents (such as **Google Antigravity**, **Cursor**, **Claude Code**, or **GitHub Copilot**).

The repository root includes [`AGENTS.md`](AGENTS.md), which defines the protocol for operational reporting:
- Directs the AI to inspect MongoDB `runs`, `locations`, and `events` collections.
- Mandates exact timestamps, count deltas (`discovered`, `updated`, `observed_openings`, `missing`), and current network breakdowns.
- Requires field-level before/after diffs for updated records while cleanly distinguishing image-only updates from operational changes (pricing, status, power, connectors).

#### Example Prompts to Ask Your AI Assistant:
- *"Give me an operational tracker update on the latest run."*
- *"What changed in the IONNA network today?"*
- *"List all newly discovered stations in Texas and Colorado."*
- *"Show me all stations that opened in the past 30 days."*
- *"Did any stations change prices or connector counts recently?"*

---

## Automated Scheduling

Keep your local tracker updated automatically with scheduled scrapes.

### Option A: macOS LaunchAgent (Recommended for Mac)

A launchd manager script is included under `bin/nightly-schedule`. It dynamically configures the agent for your checkout path and runs daily at 3:00 AM local time (wakes Mac if asleep):

```bash
# Enable nightly collection at 3:00 AM
bin/nightly-schedule on

# Check schedule status
bin/nightly-schedule status

# Trigger a test run immediately
bin/nightly-schedule run

# Tail recent logs
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

If you are using Google Antigravity, you can use the `/schedule` slash command to set up recurring collections:

```text
/schedule CronExpression="0 3 * * *" Prompt="Run python scrape.py and summarize any new station discoveries, openings, or price changes."
```

---

## Optional Headless Browser Fallback

By default, `scrape.py` uses direct HTTP requests. To enable the Playwright headless browser fallback (only invoked if direct extraction fails):

```bash
pip install -r requirements-browser.txt
playwright install chromium

# Run with browser fallback enabled
python scrape.py --browser-fallback
```

---

## Running Tests

Run the complete test suite to verify storage integration, parser logic, CLI queries, and the dashboard frontend:

```bash
# Python unit and integration tests
python -m unittest discover -s tests -v

# JavaScript dashboard frontend tests
node --test tests/test_dashboard.js
```

---

## Database Architecture

The tracker manages four collections in MongoDB:

| Collection | Purpose |
| :--- | :--- |
| `locations` | Latest known state for each unique station ID (`source_id`). Tracks active status, timestamps, and specs. |
| `observations` | Point-in-time compact snapshot for each location during every collection run. |
| `events` | Discrete lifecycle events (`discovered`, `status_changed`, `observed_open`). |
| `runs` | Metadata for each collection run: timestamp, method, payload hash, counts, baseline flag, and delta diffs. |

---

## License

MIT License. See [LICENSE](LICENSE) for details.
