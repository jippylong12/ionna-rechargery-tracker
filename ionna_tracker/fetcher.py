"""Network fetchers for retrieving the IONNA Rechargery web page.

Provides two extraction strategies:
1. `fetch_direct`: Lightweight HTTP GET with exponential backoff and retry.
   Preferred because IONNA embeds full location JSON in the server response.
2. `fetch_with_browser`: Headless Chromium fallback using Playwright in case
   IONNA modifies their map rendering to require client-side execution.
"""
from __future__ import annotations

from dataclasses import dataclass

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


@dataclass(frozen=True)
class FetchResult:
    """Encapsulates raw page HTML content and the fetch mechanism used."""

    html: str
    method: str


def fetch_direct(url: str, timeout_seconds: int = 30) -> FetchResult:
    """Fetch the target webpage directly over HTTP with automatic retry.

    Args:
        url: The web URL to fetch.
        timeout_seconds: Request timeout in seconds.

    Returns:
        FetchResult containing the raw HTML and 'http' fetch method.

    Raises:
        requests.RequestException: If the HTTP request fails after retries.
    """
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
    """Fetch the target webpage using a headless Chromium browser via Playwright.

    Used as an opt-in fallback when direct HTTP extraction fails due to client-side
    script execution requirements or dynamic rendering changes.

    Args:
        url: The web URL to navigate to.
        timeout_seconds: Navigation and selector timeout in seconds.

    Returns:
        FetchResult containing the rendered page HTML and 'headless_browser' method.

    Raises:
        RuntimeError: If playwright is not installed.
        playwright.sync_api.Error: If navigation or rendering times out.
    """
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
