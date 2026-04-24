"""
normalize_cards.py — Phase 2: Normalize raw API data to base card schema

Reads raw JSON files from cards/raw/decks/ and writes one normalized JSON
file per card into cards/STxx/. Safe to re-run — overwrites existing files
with the latest normalized output.

Usage:
    python tools/normalize_cards.py

Output:
    cards/ST01/ST01-001.json
    cards/ST01/ST01-002.json
    ...
    cards/ST04/ST04-xxx.json
"""

import json
import re
import pathlib

# ── Config ────────────────────────────────────────────────────────────────────

PROJECT_ROOT = pathlib.Path(__file__).parent.parent
RAW_DIR = PROJECT_ROOT / "cards" / "raw" / "decks"
CARDS_DIR = PROJECT_ROOT / "cards"

# Starter decks to process (must have corresponding raw files)
TARGET_DECKS = ["ST-01", "ST-02", "ST-03", "ST-04"]

# Keywords that appear as [Keyword] tokens inside card_text
KNOWN_KEYWORDS = [
    "Rush",
    "Blocker",
    "Banish",
    "Double Attack",
    "Unblockable",
]

# ── Normalizers ───────────────────────────────────────────────────────────────


def normalize_set_id(raw_set_id: str) -> str:
    """
    Convert API set_id format to our format.
    'ST-01' → 'ST01', 'OP-01' → 'OP01'
    """
    return raw_set_id.replace("-", "")


def normalize_color(raw_color: str | None) -> list[str]:
    """
    'Red' → ['Red']
    'Red/Green' → ['Red', 'Green']
    """
    if not raw_color:
        return []
    return [c.strip() for c in raw_color.split("/")]


def normalize_subtypes(raw_subtypes: str | None) -> list[str]:
    """
    'Straw Hat Crew Supernovas' → ['Straw Hat Crew', 'Supernovas']
    The API concatenates subtypes with spaces; known multi-word types are
    handled by splitting on known boundaries. For now we split naively and
    flag for review if needed.
    """
    if not raw_subtypes:
        return []
    # The API uses space separation — single-word types split cleanly,
    # multi-word types (e.g. "Straw Hat Crew") are trickier.
    # Best-effort: treat the whole string as one subtype if it has 3+ words,
    # otherwise split on spaces.
    parts = raw_subtypes.strip().split(" ")
    if len(parts) <= 2:
        return parts
    # Heuristic: known multi-word faction names
    MULTI_WORD = [
        "Straw Hat Crew",
        "Heart Pirates",
        "Kid Pirates",
        "Big Mom Pirates",
        "Beasts Pirates",
        "Seven Warlords of the Sea",
        "Animal Kingdom Pirates",
        "Whitebeard Pirates",
        "Red Hair Pirates",
        "Donquixote Pirates",
    ]
    remaining = raw_subtypes.strip()
    result = []
    for mw in MULTI_WORD:
        if mw in remaining:
            result.append(mw)
            remaining = remaining.replace(mw, "").strip()
    # Whatever's left, split by space
    if remaining:
        result.extend([p for p in remaining.split(" ") if p])
    return result if result else parts


def normalize_int(value: str | int | None) -> int | None:
    """Cast to int, return None if null/empty."""
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def extract_keywords(effect_text: str | None) -> list[str]:
    """
    Extract known keyword abilities from the effect text.
    e.g. '[Rush]' → ['Rush'], '[Blocker]' → ['Blocker']
    """
    if not effect_text:
        return []
    found = []
    for kw in KNOWN_KEYWORDS:
        pattern = rf"\[{re.escape(kw)}\]"
        if re.search(pattern, effect_text, re.IGNORECASE):
            found.append(kw)
    return found


def strip_parallel_suffix(name: str) -> str:
    """Remove trailing ' (Parallel)', ' (Alt Art)', etc. from card names."""
    return re.sub(r"\s*\(Parallel\)|\s*\(Alt Art\)|\s*\(Alt\)", "", name).strip()


def normalize_card(raw: dict) -> dict:
    """
    Transform a raw API card object into our base card schema.
    The 'triggers' field is left as [] — filled in by the DSL pipeline later.
    """
    raw_set_id = raw.get("set_id", "")
    effect_text = raw.get("card_text") or ""

    return {
        "id": raw.get("card_set_id", ""),
        "name": strip_parallel_suffix(raw.get("card_name", "")),
        "type": raw.get("card_type", ""),
        "color": normalize_color(raw.get("card_color")),
        "cost": normalize_int(raw.get("card_cost")),
        "power": normalize_int(raw.get("card_power")),
        "counter": normalize_int(raw.get("counter_amount")),
        "life": normalize_int(raw.get("life")),
        "attribute": raw.get("attribute") or None,
        "subtypes": normalize_subtypes(raw.get("sub_types")),
        "rarity": raw.get("rarity") or None,
        "set_id": normalize_set_id(raw_set_id),
        "image_id": raw.get("card_image_id") or raw.get("card_set_id", ""),
        "effect_text": effect_text.strip() if effect_text else "",
        "keywords": extract_keywords(effect_text),
        # Filled in by the DSL pipeline (Phase 3)
        "triggers": [],
        # Marker so we know DSL hasn't been applied yet
        "dsl_status": "pending",
    }


# ── Main ──────────────────────────────────────────────────────────────────────


def main():
    total_cards = 0
    total_sets = 0

    for deck_id in TARGET_DECKS:
        raw_path = RAW_DIR / f"{deck_id}.json"

        if not raw_path.exists():
            print(f"[SKIP] {deck_id} - raw file not found: {raw_path}")
            print(f"       Run fetch_cards.py first.")
            continue

        raw_cards: list[dict] = json.loads(raw_path.read_text(encoding="utf-8"))
        set_id_normalized = normalize_set_id(deck_id)  # e.g. 'ST01'
        out_dir = CARDS_DIR / set_id_normalized
        out_dir.mkdir(parents=True, exist_ok=True)

        print(f"[NORMALIZE] {deck_id} -> cards/{set_id_normalized}/ ({len(raw_cards)} cards)")

        for raw_card in raw_cards:
            normalized = normalize_card(raw_card)
            card_id = normalized["id"]

            if not card_id:
                print(f"  [WARN] Card missing ID, skipping: {raw_card}")
                continue

            out_path = out_dir / f"{card_id}.json"
            out_path.write_text(
                json.dumps(normalized, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

        total_cards += len(raw_cards)
        total_sets += 1
        print(f"  -> Written {len(raw_cards)} cards to cards/{set_id_normalized}/")

    print(f"\nDone. {total_cards} cards across {total_sets} sets written to {CARDS_DIR}")


if __name__ == "__main__":
    main()
