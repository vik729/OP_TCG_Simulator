"""
fetch_cards.py — Phase 1: Fetch raw card data from optcgapi.com

Pulls all cards for the target starter decks and saves raw API responses as
local JSON files in cards/raw/decks/. Safe to re-run — skips files that
already exist.

Usage:
    python tools/fetch_cards.py

Output:
    cards/raw/decks/ST-01.json
    cards/raw/decks/ST-02.json
    cards/raw/decks/ST-03.json
    cards/raw/decks/ST-04.json
"""

import json
import time
import pathlib
import urllib.request
import urllib.error

# ── Config ────────────────────────────────────────────────────────────────────

BASE_URL = "https://optcgapi.com/api"

# Starter decks to fetch (extend this list later to add more sets)
TARGET_DECKS = ["ST-01", "ST-02", "ST-03", "ST-04"]

# Output directory (gitignored — never committed)
RAW_DIR = pathlib.Path(__file__).parent.parent / "cards" / "raw" / "decks"

# Polite delay between API calls (seconds)
REQUEST_DELAY = 0.5

# ── Helpers ───────────────────────────────────────────────────────────────────


def fetch_json(url: str) -> list | dict:
    """Fetch a URL and return the parsed JSON response."""
    print(f"  GET {url}")
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "OP_TCG_Simulator/0.1 (educational fan project)"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_deck(deck_id: str) -> list[dict]:
    """Fetch all cards for a given starter deck ID (e.g. 'ST-01')."""
    url = f"{BASE_URL}/decks/{deck_id}/"
    return fetch_json(url)


def deduplicate(cards: list[dict]) -> list[dict]:
    """
    Keep only the first (canonical) entry per card_set_id.
    The API returns parallel/foil variants as separate entries with the same ID.
    """
    seen = set()
    unique = []
    for card in cards:
        card_id = card.get("card_set_id")
        if card_id and card_id not in seen:
            seen.add(card_id)
            unique.append(card)
    return unique


# ── Main ──────────────────────────────────────────────────────────────────────


def main():
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    for deck_id in TARGET_DECKS:
        out_path = RAW_DIR / f"{deck_id}.json"

        if out_path.exists():
            print(f"[SKIP] {deck_id} - already cached at {out_path}")
            continue

        print(f"[FETCH] {deck_id}")
        try:
            cards = fetch_deck(deck_id)
        except urllib.error.URLError as e:
            print(f"  [ERROR] Failed to fetch {deck_id}: {e}")
            continue

        cards = deduplicate(cards)
        print(f"  -> {len(cards)} unique cards")

        out_path.write_text(
            json.dumps(cards, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"  -> Saved to {out_path}")

        time.sleep(REQUEST_DELAY)

    print("\nDone. Raw files saved to:", RAW_DIR)


if __name__ == "__main__":
    main()
