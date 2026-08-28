#!/usr/bin/env python3
"""Flask application server for the IONNA Rechargery Tracker dashboard.

Serves:
- `GET /`: Interactive web dashboard user interface.
- `GET /api/dashboard`: Aggregated network metrics, history, and active station list.
- `GET /api/health`: Database connection and server readiness health check.
"""
from __future__ import annotations

from flask import Flask, jsonify, render_template, request
from pymongo.errors import PyMongoError

from ionna_tracker.analytics import dashboard_data
from ionna_tracker.config import Settings
from ionna_tracker.storage import connect


def create_app(settings: Settings | None = None) -> Flask:
    """Application factory for the IONNA Rechargery Tracker web dashboard.

    Args:
        settings: Optional Settings instance (uses defaults from environment if omitted).

    Returns:
        Configured Flask application instance.
    """
    settings = settings or Settings()
    app = Flask(__name__)
    client, db = connect(settings.mongodb_uri, settings.mongodb_database)
    app.extensions["mongo_client"] = client
    app.extensions["mongo_db"] = db

    @app.get("/")
    def index():
        """Render the dashboard HTML interface."""
        return render_template("index.html")

    @app.get("/api/dashboard")
    def dashboard():
        """Return complete dashboard analytics payload as JSON.

        Query Params:
            days: Lookback window in days for recent events (default: 7).
        """
        try:
            days = max(1, min(int(request.args.get("days", "7")), 3650))
        except ValueError:
            return jsonify({"error": "days must be an integer"}), 400
        try:
            return jsonify(dashboard_data(db, days))
        except PyMongoError as exc:
            app.logger.exception("MongoDB query failed")
            return jsonify({"error": f"MongoDB unavailable: {exc}"}), 503

    @app.get("/api/health")
    def health():
        """Check database connectivity and service health."""
        try:
            client.admin.command("ping")
            return jsonify({"ok": True, "database": settings.mongodb_database})
        except PyMongoError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 503

    return app


if __name__ == "__main__":
    active_settings = Settings()
    create_app(active_settings).run(
        host="127.0.0.1",
        port=active_settings.port,
        debug=active_settings.flask_debug,
    )
