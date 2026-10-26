# Credit Card Airport Lounge Eligibility Tracker

A small data and scraping framework for tracking airport lounge access offered by bank cards. It records the eligible card, lounge network, visit limits, spend-based eligibility conditions, add-on card access rules, and lounges by airport and terminal.

## Eligibility model

- **Primary card:** Store the quarterly visit limit and any spend threshold/period required to unlock or retain lounge visits. A threshold may be absent when no spend condition applies.
- **Add-on card:** Each product records whether an add-on card has a **shared quota** with the primary card, an **independent quota**, or **no access**. Check the issuer's current terms for the precise policy.
- **Lounges:** Store the airport code, terminal, and lounge name for each known eligible location.
- **Verification:** `last_verified` records when the entry was last checked. Lounge access terms and participating locations can change, so confirm them with the issuer before travel.

## Repository layout

- `data/cards.json` — card data store (starts with an empty card list).
- `data/cards.schema.json` — JSON Schema describing and validating the card data format.
- `scraper.py` — reusable fetch, parse, and JSON upsert framework. The default parser is intentionally generic; implement a source-specific parser for each issuer's page and respect its terms of use and robots policy.
- `requirements.txt` — Python dependencies.

## Setup

Create and activate a virtual environment from the project root:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

For Playwright browser automation, install a browser once after installing dependencies:

```sh
python -m playwright install chromium
```

Deactivate the environment with `deactivate` when finished. The `.venv/` directory is ignored by Git.

## Scraper usage

Implement a parser that accepts a `requests.Response` and returns one card object following `data/cards.json`'s structure, then configure an issuer URL and call the update workflow. The framework writes atomically and upserts by stable `id`, so repeated updates replace the existing card record instead of duplicating it. Only use sources you are authorized to access, and verify extracted eligibility details against official issuer terms.

## Data shape

Each card entry has a stable `id`, card name, issuer, network, primary-card quarterly visits and spend conditions, add-on-card rule, eligible lounge list, and ISO-8601 `last_verified` timestamp. See `data/cards.json` for the canonical structure.
