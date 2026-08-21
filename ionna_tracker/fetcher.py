from __future__ import annotations

from dataclasses import dataclass

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


@dataclass(frozen=True)
class FetchResult:
    html: str
    method: str


def fetch_direct(url: str, timeout_seconds: int = 30) -> FetchResult:
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        backoff_factor=0.6,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
    )
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))
    response = session.get(
        url,
        timeout=timeout_seconds,
        headers={
            "User-Agent": (
                "IONNA-Rechargery-Tracker/1.0 "
                "(+local personal analytics; one page per manual run)"
            ),
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    response.raise_for_status()
    return FetchResult(response.text, "http")


def fetch_with_browser(url: str, timeout_seconds: int = 45) -> FetchResult:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Browser fallback requires: pip install -r requirements-browser.txt "
            "and playwright install chromium"
        ) from exc

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=timeout_seconds * 1000,
            )
            page.wait_for_selector("script", timeout=timeout_seconds * 1000)
            return FetchResult(page.content(), "headless_browser")
        finally:
            browser.close()
