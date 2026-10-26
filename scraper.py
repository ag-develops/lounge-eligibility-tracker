"""Reusable framework for collecting issuer lounge eligibility data.

Issuer pages are not uniform. This starter expects a source-specific parser to
return card dictionaries in the documented schema; ``parse_embedded_cards`` is
provided for pages exposing a JSON payload in a designated script element.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

LOGGER = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_DATA_FILE = PROJECT_ROOT / "data" / "cards.json"
ALLOWED_NETWORKS = {
    "DreamFolks",
    "Priority Pass",
    "LoungeKey",
    "Visa",
    "Mastercard",
    "RuPay",
}
ALLOWED_ADD_ON_RULES = {"shared_quota", "independent_quota", "no_access"}


class ScraperError(Exception):
    """Raised when a page cannot be fetched, parsed, or saved safely."""


def fetch_page(url: str, *, timeout: float = 20.0) -> str:
    """Fetch an issuer page with a timeout and actionable HTTP errors."""
    parsed_url = urlparse(url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        raise ValueError("url must be an absolute http(s) URL")

    try:
        response = requests.get(
            url,
            timeout=timeout,
            headers={"User-Agent": "LoungeEligibilityTracker/0.1 (+manual research tool)"},
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise ScraperError(f"Could not fetch {url}: {exc}") from exc
    return response.text


def parse_embedded_cards(
    html: str, *, element_id: str = "lounge-card-data"
) -> list[dict[str, Any]]:
    """Read card objects from a JSON script element in an issuer page.

    Expected element: ``<script type="application/json" id="lounge-card-data">``.
    The payload may be one card object or a list of card objects. For ordinary
    issuer pages, replace this with a parser tailored to the page's markup/API.
    """
    soup = BeautifulSoup(html, "html.parser")
    element = soup.find("script", id=element_id, type="application/json")
    if element is None or not element.string and not element.get_text(strip=True):
        raise ScraperError(f"No JSON payload found in script element #{element_id}")

    try:
        payload = json.loads(element.string or element.get_text())
    except json.JSONDecodeError as exc:
        raise ScraperError(f"Invalid JSON in script element #{element_id}: {exc}") from exc

    cards = payload if isinstance(payload, list) else [payload]
    if not all(isinstance(card, dict) for card in cards):
        raise ScraperError("Card payload must be an object or a list of objects")
    return cards


def validate_card(card: dict[str, Any]) -> None:
    """Validate the required card fields and supported rule values."""
    required = {
        "id",
        "card_name",
        "issuer",
        "network",
        "primary_card",
        "add_on_card_rule",
        "eligible_lounges",
        "last_verified",
    }
    missing = required - card.keys()
    if missing:
        raise ValueError(f"Card is missing required fields: {', '.join(sorted(missing))}")
    if card["network"] not in ALLOWED_NETWORKS:
        raise ValueError(f"Unsupported network: {card['network']!r}")
    if card["add_on_card_rule"] not in ALLOWED_ADD_ON_RULES:
        raise ValueError(f"Unsupported add-on rule: {card['add_on_card_rule']!r}")
    if not isinstance(card["primary_card"], dict):
        raise ValueError("primary_card must be an object")
    if not isinstance(card["eligible_lounges"], list):
        raise ValueError("eligible_lounges must be a list")
    try:
        datetime.fromisoformat(card["last_verified"].replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise ValueError("last_verified must be an ISO-8601 timestamp") from exc

    for lounge in card["eligible_lounges"]:
        if not isinstance(lounge, dict) or not {
            "airport_code",
            "terminal",
            "lounge_name",
        }.issubset(lounge):
            raise ValueError(
                "Each lounge must include airport_code, terminal, and lounge_name"
            )


def update_cards_json(
    cards: list[dict[str, Any]], data_file: Path = DEFAULT_DATA_FILE
) -> int:
    """Upsert cards by ``id`` and atomically write the JSON document.

    Returns the number of card records inserted or updated.
    """
    for card in cards:
        validate_card(card)

    data_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        document = json.loads(data_file.read_text(encoding="utf-8"))
    except FileNotFoundError:
        document = {"schema_version": 1, "cards": []}
    except (OSError, json.JSONDecodeError) as exc:
        raise ScraperError(f"Could not read {data_file}: {exc}") from exc

    if not isinstance(document, dict) or not isinstance(document.get("cards"), list):
        raise ScraperError(f"{data_file} must contain an object with a cards list")

    by_id = {card.get("id"): card for card in document["cards"] if card.get("id")}
    for card in cards:
        by_id[card["id"]] = card
    document["schema_version"] = 1
    document["cards"] = list(by_id.values())

    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=data_file.parent, delete=False
        ) as temp_file:
            json.dump(document, temp_file, indent=2, ensure_ascii=False)
            temp_file.write("\n")
            temp_path = Path(temp_file.name)
        os.replace(temp_path, data_file)
    except OSError as exc:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise ScraperError(f"Could not write {data_file}: {exc}") from exc
    return len(cards)


def scrape_and_update(
    url: str,
    parser: Callable[[str], list[dict[str, Any]]] = parse_embedded_cards,
    *,
    data_file: Path = DEFAULT_DATA_FILE,
    timeout: float = 20.0,
) -> int:
    """Fetch a page, parse its cards, and upsert them into the JSON store."""
    html = fetch_page(url, timeout=timeout)
    cards = parser(html)
    return update_cards_json(cards, data_file)


def main() -> int:
    """Run against LOUNGE_SOURCE_URL when configured in the environment."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    url = os.environ.get("LOUNGE_SOURCE_URL")
    if not url:
        LOGGER.error("Set LOUNGE_SOURCE_URL to an authorized issuer page URL.")
        return 2
    try:
        count = scrape_and_update(url)
    except (ScraperError, ValueError) as exc:
        LOGGER.error("Scrape failed: %s", exc)
        return 1
    LOGGER.info("Inserted or updated %d card record(s).", count)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
