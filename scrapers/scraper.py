"""Conservatively check issuer pages and refresh recognized lounge rules.

Only explicit, recognizable values are changed. Unsupported page layouts are
reported instead of being guessed; verify issuer terms before relying on them.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup

LOGGER = logging.getLogger("lounge_scraper")
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_FILE = PROJECT_ROOT / "data" / "cards.json"
USER_AGENT = "LoungeEligibilityTracker/1.0 (+manual eligibility research)"


def load_cards(path: Path) -> dict[str, Any]:
    """Load and minimally validate the card data document."""
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read valid card data from {path}: {exc}") from exc
    if not isinstance(document, dict) or not isinstance(document.get("cards"), list):
        raise ValueError("Card data must be an object containing a cards array")
    for card in document["cards"]:
        if not isinstance(card, dict) or not card.get("id") or not card.get("source_url"):
            raise ValueError("Every card must have an id and source_url")
    return document


def fetch_html(url: str, *, timeout: float, browser: bool) -> str:
    """Fetch an issuer page using Requests or an opt-in Playwright browser."""
    if browser:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser_instance = playwright.chromium.launch(headless=True)
            try:
                page = browser_instance.new_page(user_agent=USER_AGENT)
                response = page.goto(url, wait_until="domcontentloaded", timeout=int(timeout * 1000))
                if response is not None and response.status >= 400:
                    raise requests.HTTPError(f"HTTP {response.status} for {url}")
                return page.content()
            finally:
                browser_instance.close()

    response = requests.get(
        url,
        headers={"User-Agent": USER_AGENT},
        timeout=timeout,
    )
    response.raise_for_status()
    return response.text


def _money_amount(text: str) -> float | None:
    """Parse an INR amount only when it is marked by ₹ or INR."""
    match = re.search(r"(?:₹\s*|INR\s*)([\d,]+(?:\.\d+)?)", text, re.IGNORECASE)
    if match is None:
        return None
    return float(match.group(1).replace(",", ""))


def extract_rule_updates(card: dict[str, Any], html: str) -> dict[str, Any]:
    """Extract clearly labeled quarterly visits and spend conditions.

    The parser deliberately requires lounge-related quarterly wording and an
    explicitly marked INR amount. If a bank changes its page layout or language,
    it leaves the existing rule intact for manual review.
    """
    soup = BeautifulSoup(html, "html.parser")
    text = " ".join(soup.stripped_strings)
    text = re.sub(r"\s+", " ", text)
    proposed: dict[str, Any] = {}

    visit_match = re.search(
        r"\b(\d{1,2})\s+(?:complimentary\s+)?(?:domestic\s+)?"
        r"(?:airport\s+)?lounge\s+(?:visits?|access)\b"
        r"[^.]{0,100}?(?:\b(?:per|each|every)\s+quarter\b|\bquarterly\b)",
        text,
        re.IGNORECASE,
    )
    if visit_match:
        proposed["quarterly_visit_limit"] = int(visit_match.group(1))

    spend_text = " ".join(
        fragment
        for fragment in re.split(r"(?<=[.!?])\s+|\s*\|\s*", text)
        if "lounge" in fragment.lower()
        and re.search(r"\b(?:preceding|previous|prior)\b.{0,45}\bquarter\b", fragment, re.I)
        and re.search(r"\bspend(?:s|ing)?\b", fragment, re.I)
    )
    amount = _money_amount(spend_text)
    if amount is not None:
        period_match = re.search(
            r"\b((?:preceding|previous|prior)(?:\s+spends?)?\s+quarter)\b",
            spend_text,
            re.IGNORECASE,
        )
        proposed["spend_conditions"] = [
            {
                "amount": amount,
                "currency": "INR",
                "period": re.sub(r"\s+", "_", period_match.group(1).lower())
                if period_match
                else "preceding_quarter",
                "description": spend_text[:500].strip(),
            }
        ]

    return proposed


def _table_lounges(soup: BeautifulSoup) -> list[dict[str, str]]:
    """Extract lounge rows only from tables with recognizable column headers."""
    extracted: list[dict[str, str]] = []
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if not rows:
            continue
        headers = [cell.get_text(" ", strip=True).lower() for cell in rows[0].find_all(["th", "td"])]
        airport_col = next(
            (i for i, value in enumerate(headers) if "airport" in value or "airport code" in value),
            None,
        )
        terminal_col = next((i for i, value in enumerate(headers) if "terminal" in value), None)
        lounge_col = next(
            (i for i, value in enumerate(headers) if "lounge" in value and "access" not in value),
            None,
        )
        if airport_col is None or terminal_col is None or lounge_col is None:
            continue

        for row in rows[1:]:
            cells = [cell.get_text(" ", strip=True) for cell in row.find_all(["th", "td"])]
            if max(airport_col, terminal_col, lounge_col) >= len(cells):
                continue
            code_match = re.search(r"\b([A-Z]{3,4})\b", cells[airport_col])
            terminal = cells[terminal_col].strip()
            lounge_name = cells[lounge_col].strip()
            if code_match and terminal and lounge_name:
                extracted.append(
                    {
                        "airport_code": code_match.group(1),
                        "terminal": terminal,
                        "lounge_name": lounge_name,
                    }
                )
    return extracted


def extract_updates(card: dict[str, Any], html: str) -> dict[str, Any]:
    """Combine recognized rule and lounge-list changes for a card."""
    soup = BeautifulSoup(html, "html.parser")
    updates: dict[str, Any] = {}
    primary_updates = extract_rule_updates(card, html)

    if "quarterly_visit_limit" in primary_updates:
        current = card["primary_card"].get("quarterly_visit_limit")
        if current != primary_updates["quarterly_visit_limit"]:
            updates.setdefault("primary_card", {})["quarterly_visit_limit"] = primary_updates[
                "quarterly_visit_limit"
            ]
    if "spend_conditions" in primary_updates:
        current = card["primary_card"].get("spend_conditions", [])
        if current != primary_updates["spend_conditions"]:
            updates.setdefault("primary_card", {})["spend_conditions"] = primary_updates[
                "spend_conditions"
            ]

    lounges = _table_lounges(soup)
    if lounges and card.get("eligible_lounges") != lounges:
        updates["eligible_lounges"] = lounges
    return updates


def _merge(target: dict[str, Any], updates: dict[str, Any]) -> None:
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _merge(target[key], value)
        else:
            target[key] = value


def write_json_atomic(path: Path, document: dict[str, Any]) -> None:
    """Write JSON through a temporary file to avoid partial updates."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False
        ) as temporary_file:
            json.dump(document, temporary_file, indent=2, ensure_ascii=False)
            temporary_file.write("\n")
            temporary_path = Path(temporary_file.name)
        os.replace(temporary_path, path)
    except OSError:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise


def refresh_cards(
    data_file: Path,
    *,
    card_ids: set[str] | None = None,
    browser: bool = False,
    check_only: bool = False,
    timeout: float = 20.0,
    delay: float = 1.0,
) -> int:
    """Check selected issuer pages and save recognized changes.

    Returns the count of card records that were updated or verified.
    """
    document = load_cards(data_file)
    changed_count = 0
    errors = 0
    for card in document["cards"]:
        if card_ids and card["id"] not in card_ids:
            continue
        try:
            html = fetch_html(card["source_url"], timeout=timeout, browser=browser)
            updates = extract_updates(card, html)
        except (requests.RequestException, ValueError, RuntimeError) as exc:
            LOGGER.error("%s: could not check issuer page: %s", card["id"], exc)
            errors += 1
            continue
        except Exception as exc:
            # Playwright may raise its own browser/timeout exception types.
            if browser:
                LOGGER.error("%s: browser fetch failed: %s", card["id"], exc)
                errors += 1
                continue
            raise

        if updates:
            LOGGER.warning("%s: detected rule changes: %s", card["id"], json.dumps(updates, ensure_ascii=False))
            _merge(card, updates)
            changed_count += 1
        else:
            LOGGER.info("%s: no recognized structured rule changes", card["id"])

        card["last_verified"] = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        if delay:
            time.sleep(delay)

    if card_ids:
        found_ids = {card["id"] for card in document["cards"]}
        missing_ids = card_ids - found_ids
        if missing_ids:
            LOGGER.error("Unknown card id(s): %s", ", ".join(sorted(missing_ids)))
            errors += len(missing_ids)

    if not check_only and changed_count + (len(document["cards"]) if not card_ids else len(card_ids)) > 0:
        write_json_atomic(data_file, document)
    if check_only:
        LOGGER.info("Check-only mode: no data was written")
    if errors:
        raise RuntimeError(f"Completed with {errors} page or selection error(s)")
    return changed_count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA_FILE, help="cards JSON path")
    parser.add_argument("--card-id", action="append", dest="card_ids", help="limit to a card id (repeatable)")
    parser.add_argument("--browser", action="store_true", help="render pages with Playwright")
    parser.add_argument("--check-only", action="store_true", help="detect changes without writing JSON")
    parser.add_argument("--timeout", type=float, default=20.0, help="page timeout in seconds")
    parser.add_argument("--delay", type=float, default=1.0, help="seconds between issuer requests")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        changed = refresh_cards(
            args.data,
            card_ids=set(args.card_ids) if args.card_ids else None,
            browser=args.browser,
            check_only=args.check_only,
            timeout=args.timeout,
            delay=args.delay,
        )
    except (ValueError, RuntimeError, OSError) as exc:
        LOGGER.error("Scrape run failed: %s", exc)
        return 1
    LOGGER.info("Updated %d card record(s).", changed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
