"""
fetch_all_sets.py — Pull raw card data for every available set.

The optcgapi serves starter decks at /api/decks/{ID}/ and booster/extra sets
at /api/sets/{ID}/. This script tries a wide enumeration of set IDs at both
endpoints and saves whatever returns 200. Skips files that already exist.

Usage:
    python tools/fetch_all_sets.py

Output:
    cards/raw/decks/{ID}.json     # for ST-XX (starter decks)
    cards/raw/sets/{ID}.json      # for OP-XX, EB-XX (booster + extra)
"""
import json
import time
import pathlib
import urllib.request
import urllib.error


BASE_URL = "https://optcgapi.com/api"
ROOT = pathlib.Path(__file__).parent.parent / "cards" / "raw"
DECKS_DIR = ROOT / "decks"
SETS_DIR = ROOT / "sets"
REQUEST_DELAY = 0.5
USER_AGENT = "OP_TCG_Simulator/0.2 (educational fan project)"


def fetch_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def deduplicate(cards):
    seen = set()
    unique = []
    for card in cards:
        cid = card.get("card_set_id")
        if cid and cid not in seen:
            seen.add(cid)
            unique.append(card)
    return unique


def try_fetch(endpoint: str, set_id: str, out_dir: pathlib.Path) -> str:
    out_path = out_dir / f"{set_id}.json"
    if out_path.exists():
        return f"SKIP {set_id} (cached)"
    url = f"{BASE_URL}/{endpoint}/{set_id}/"
    try:
        cards = fetch_json(url)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return f"404  {set_id}"
        return f"ERR  {set_id}: {e}"
    except Exception as e:
        return f"ERR  {set_id}: {e}"
    if not isinstance(cards, list):
        return f"BAD  {set_id}: not a list"
    cards = deduplicate(cards)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(cards, indent=2, ensure_ascii=False),
                        encoding="utf-8")
    return f"OK   {set_id} -> {len(cards)} cards"


def main():
    # Enumerate everything plausible. Failures are silently skipped.
    starter_ids = [f"ST-{i:02d}" for i in range(1, 30)]
    op_ids = [f"OP-{i:02d}" for i in range(1, 15)]
    eb_ids = [f"EB-{i:02d}" for i in range(1, 5)]
    prb_ids = [f"PRB-{i:02d}" for i in range(1, 3)]

    print(f"== Starter decks (ST-XX) via /decks/ ==")
    for sid in starter_ids:
        result = try_fetch("decks", sid, DECKS_DIR)
        print(f"  {result}")
        if result.startswith("OK"):
            time.sleep(REQUEST_DELAY)

    print(f"\n== Booster sets (OP-XX) via /sets/ ==")
    for sid in op_ids:
        result = try_fetch("sets", sid, SETS_DIR)
        print(f"  {result}")
        if result.startswith("OK"):
            time.sleep(REQUEST_DELAY)

    print(f"\n== Extra boosters (EB-XX) via /sets/ ==")
    for sid in eb_ids:
        result = try_fetch("sets", sid, SETS_DIR)
        print(f"  {result}")
        if result.startswith("OK"):
            time.sleep(REQUEST_DELAY)

    print(f"\n== Premium boosters (PRB-XX) via /sets/ ==")
    for sid in prb_ids:
        result = try_fetch("sets", sid, SETS_DIR)
        print(f"  {result}")
        if result.startswith("OK"):
            time.sleep(REQUEST_DELAY)

    # Summary
    print("\n== Summary ==")
    deck_files = sorted(DECKS_DIR.glob("*.json")) if DECKS_DIR.exists() else []
    set_files = sorted(SETS_DIR.glob("*.json")) if SETS_DIR.exists() else []
    print(f"  Starter decks: {len(deck_files)} files")
    print(f"  Booster sets:  {len(set_files)} files")
    total_cards = 0
    for f in deck_files + set_files:
        data = json.loads(f.read_text(encoding="utf-8"))
        total_cards += len(data) if isinstance(data, list) else 0
    print(f"  Total cards (deduplicated):  {total_cards}")


if __name__ == "__main__":
    main()
