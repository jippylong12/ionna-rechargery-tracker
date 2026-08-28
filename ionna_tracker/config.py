"""Configuration management for the IONNA Rechargery Tracker.

Loads environment variables from `.env` or system environment and provides
a strongly-typed, immutable settings dataclass for database connection,
scraping targets, and web server configuration.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

# Load environment variables from local .env file if present
load_dotenv()


@dataclass(frozen=True)
class Settings:
    """Application runtime settings and configuration defaults."""

    mongodb_uri: str = os.getenv("MONGODB_URI", "mongodb://127.0.0.1:27017")
    mongodb_database: str = os.getenv(
        "MONGODB_DATABASE", "ionna_rechargery_tracker"
    )
    source_url: str = os.getenv(
        "IONNA_SOURCE_URL",
        "https://www.ionna.com/rechargeries/find-a-rechargery/",
    )
    port: int = int(os.getenv("PORT", "5050"))
    flask_debug: bool = os.getenv("FLASK_DEBUG", "0").lower() in {
        "1",
        "true",
        "yes",
    }
