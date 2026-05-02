"""
engine/deck.py
==============
Deck loading and validation.

Two loaders:
  load_official_deck(deck_id, db) - reads cards/raw/decks/{deck_id}.json
  load_custom_deck(path, db) - reads a custom YAML decklist

One validator:
  validate_deck(deck, db, ruleset) - raises DeckValidationError on first violation.

Validation rules (per rules section 5-1-2):
  1. Leader card has type == "Leader"
  2. Exactly 50 main-deck cards
  3. Color rule (5-1-2-2): every card's colors sub leader's colors
  4. Multiplicity (5-1-2-3): max 4 of any card_id
  5. Banlist: no card_id in ruleset.banlist
  6. Existence: every card_id resolves in CardDB

Note on official deck format: cards/raw/decks/ST-XX.json contains the SET
contents (one entry per unique card), NOT a decklist with multiplicities.
load_official_deck synthesizes a 50-card deck by taking 4 of each non-Leader
card sorted by id, truncating at 50. Real Bandai starter deck composition
isn't exposed by optcgapi.
"""
from __future__ import annotations
import json
import yaml
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from engine.card_db import CardDB
from engine.ruleset import Ruleset


class DeckValidationError(Exception):
    pass


@dataclass(frozen=True)
class DeckList:
    leader_id: str
    main_deck_ids: tuple[str, ...]   # 50 entries with duplicates per multiplicity
    don_count: int = 10


def load_official_deck(deck_id: str, db: CardDB) -> DeckList:
    """Load from cards/raw/decks/{deck_id}.json.

    The optcgapi format gives us set contents (one entry per unique card,
    no multiplicities). We synthesize a 50-card deck by taking 4 of each
    non-Leader card sorted by id, then truncating to exactly 50.
    """
    path = Path("cards") / "raw" / "decks" / f"{deck_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"Official deck not found: {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))

    leader_id: str | None = None
    non_leader_ids: list[str] = []
    for entry in raw:
        cid = entry.get("card_set_id") or entry.get("id")
        if not cid:
            continue
        ctype = entry.get("card_type") or entry.get("type", "")
        if ctype == "Leader":
            leader_id = cid
        else:
            non_leader_ids.append(cid)

    if leader_id is None:
        raise DeckValidationError(f"Official deck {deck_id} has no Leader card")

    # Synthesize 50-card deck: 4 of each non-leader, sorted by id, truncated to 50
    sorted_ids = sorted(set(non_leader_ids))
    main_ids: list[str] = []
    for cid in sorted_ids:
        for _ in range(4):
            main_ids.append(cid)
            if len(main_ids) == 50:
                break
        if len(main_ids) == 50:
            break

    # If we couldn't reach 50 (unlikely), pad by duplicating the last card
    while len(main_ids) < 50:
        main_ids.append(sorted_ids[0])

    return DeckList(leader_id=leader_id, main_deck_ids=tuple(main_ids))


def load_custom_deck(path: Path, db: CardDB) -> DeckList:
    """Load from a YAML decklist file.

    Format:
        leader: <card_id>
        main_deck:
          - {id: <card_id>, count: <int>}
          ...
    """
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    leader_id = data["leader"]
    main_ids: list[str] = []
    for entry in data["main_deck"]:
        main_ids.extend([entry["id"]] * int(entry["count"]))
    return DeckList(leader_id=leader_id, main_deck_ids=tuple(main_ids))


def validate_deck(deck: DeckList, db: CardDB, ruleset: Ruleset) -> None:
    """Validate per rules section 5-1-2. Raises DeckValidationError on first violation."""
    # Rule 6: Existence - leader
    try:
        leader_def = db.get(deck.leader_id)
    except KeyError:
        raise DeckValidationError(f"Unknown leader card: {deck.leader_id}")

    # Rule 1: Leader is type "Leader"
    if leader_def.type != "Leader":
        raise DeckValidationError(
            f"Card {deck.leader_id} is type {leader_def.type!r}, not Leader"
        )

    # Rule 2: Exactly 50 main-deck cards
    if len(deck.main_deck_ids) != 50:
        raise DeckValidationError(
            f"Main deck has {len(deck.main_deck_ids)} cards, expected 50"
        )

    leader_colors = set(leader_def.color)

    # Rule 5: banlist; Rule 6: Existence; Rule 3: color
    for cid in deck.main_deck_ids:
        if cid in ruleset.banlist:
            raise DeckValidationError(f"Card {cid} is banned in ruleset {ruleset.id}")
        try:
            cdef = db.get(cid)
        except KeyError:
            raise DeckValidationError(f"Unknown card in deck: {cid}")
        card_colors = set(cdef.color)
        if card_colors and not (card_colors & leader_colors):
            raise DeckValidationError(
                f"Card {cid} colors {card_colors} share no color with leader {leader_colors}"
            )

    # Rule 4: Multiplicity - max 4 per card_id
    counts = Counter(deck.main_deck_ids)
    most_common_id, most_common_count = counts.most_common(1)[0]
    if most_common_count > 4:
        raise DeckValidationError(
            f"Card {most_common_id} appears {most_common_count} times, max is 4"
        )
