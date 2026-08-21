#!/usr/bin/env python3
from __future__ import annotations

from flask import Flask, jsonify, render_template, request
from pymongo.errors import PyMongoError

from ionna_tracker.analytics import dashboard_data
from ionna_tracker.config import Settings
from ionna_tracker.storage import connect


def create_app(settings: Settings | None = None) -> Flask:
    settings = settings or Settings()
    app = Flask(__name__)
    client, db = connect(settings.mongodb_uri, settings.mongodb_database)
    app.extensions["mongo_client"] = client
    app.extensions["mongo_db"] = db

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/api/dashboard")
    def dashboard():
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
