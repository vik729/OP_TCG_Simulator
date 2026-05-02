"""
engine/card_db.py
=================
Card definition loader and lookup.

Loads cards/STxx/*.json into typed CardDefinition dataclasses. Merges
keyword data from cards/keywords/STxx.yaml and applies overrides from
cards/keyword_overrides.yaml (currently empty).

Triggers and conditional_keywords are always empty in vanilla MVP — the
DSL phase will populate them.
"""
from __future__ import annotations
import json
import yaml
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Iterator, Any


KNOWN_KEYWORDS = (
    "Blocker", "Rush", "Banish", "Double Attack", "Unblockable", "Rush: Character",
)


@dataclass(frozen=True)
class ConditionalKeywordGrant:
    """A keyword granted to the card when a condition is met (e.g. [DON!! x2] [Rush])."""
    keyword: str
    condition: dict


@dataclass(frozen=True)
class CardDefinition:
    """Static, immutable definition of a card. One per card_set_id."""
    id: str
    name: str
    type: str                       # "Leader" | "Character" | "Event" | "Stage"
    color: tuple[str, ...]
    cost: Optional[int]
    power: Optional[int]
    counter: Optional[int]
    life: Optional[int]
    attribute: Optional[str]
    subtypes: tuple[str, ...]
    keywords: tuple[str, ...]
    conditional_keywords: tuple[ConditionalKeywordGrant, ...]
    triggers: tuple[dict, ...]
    effect_text: str
    set_id: str


def _extract_keywords_from_text(effect_text: str) -> tuple[str, ...]:
    """Naive regex: any KNOWN_KEYWORDS appearing in [brackets] is included.
    Used as a fallback when no YAML entry exists for the card.
    Smart, position-aware regex deferred — see docs/todos/SMART_KEYWORD_REGEX.md.
    """
    if not effect_text:
        return ()
    found = []
    for kw in KNOWN_KEYWORDS:
        if f"[{kw}]" in effect_text:
            found.append(kw)
    return tuple(found)


class CardDB:
    """Loads and serves card definitions."""

    def __init__(self, cards_root: Path = Path("cards")) -> None:
        self.cards_root = Path(cards_root)
        self._cards: dict[str, CardDefinition] = {}
        self._load_all()

    def _load_keyword_yaml(self, set_id: str) -> dict[str, list[str]]:
        path = self.cards_root / "keywords" / f"{set_id}.yaml"
        if not path.exists():
            return {}
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return data or {}

    def _load_overrides(self) -> dict[str, dict[str, list[str]]]:
        path = self.cards_root / "keyword_overrides.yaml"
        if not path.exists():
            return {}
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return data or {}

    def _resolve_keywords(self, card_id: str, set_id: str, effect_text: str,
                          yaml_data: dict[str, list[str]],
                          overrides: dict[str, dict[str, list[str]]]) -> tuple[str, ...]:
        # Priority 1: hand-authored YAML
        if card_id in yaml_data:
            kws = list(yaml_data[card_id] or [])
        else:
            # Priority 2: naive regex fallback
            kws = list(_extract_keywords_from_text(effect_text))
        # Priority 3: override file
        override = overrides.get(card_id, {})
        for kw in override.get("remove", []):
            if kw in kws:
                kws.remove(kw)
        for kw in override.get("add", []):
            if kw not in kws:
                kws.append(kw)
        return tuple(kws)

    def _load_one_card(self, json_path: Path, set_id: str,
                       yaml_data: dict[str, list[str]],
                       overrides: dict[str, dict[str, list[str]]]) -> CardDefinition:
        raw = json.loads(json_path.read_text(encoding="utf-8"))
        card_id = raw["id"]
        keywords = self._resolve_keywords(
            card_id, set_id, raw.get("effect_text", "") or "", yaml_data, overrides
        )
        return CardDefinition(
            id=card_id,
            name=raw.get("name", ""),
            type=raw.get("type", ""),
            color=tuple(raw.get("color") or ()),
            cost=raw.get("cost"),
            power=raw.get("power"),
            counter=raw.get("counter"),
            life=raw.get("life"),
            attribute=raw.get("attribute"),
            subtypes=tuple(raw.get("subtypes") or ()),
            keywords=keywords,
            conditional_keywords=(),     # vanilla MVP: never populated
            triggers=(),                  # vanilla MVP: never populated
            effect_text=raw.get("effect_text", "") or "",
            set_id=raw.get("set_id", set_id),
        )

    def _load_all(self) -> None:
        overrides = self._load_overrides()
        for set_dir in sorted(self.cards_root.iterdir()):
            if not set_dir.is_dir():
                continue
            if set_dir.name in ("raw", "keywords"):
                continue
            set_id = set_dir.name
            yaml_data = self._load_keyword_yaml(set_id)
            for json_path in sorted(set_dir.glob("*.json")):
                card = self._load_one_card(json_path, set_id, yaml_data, overrides)
                self._cards[card.id] = card

    def get(self, definition_id: str) -> CardDefinition:
        return self._cards[definition_id]

    def all_definitions(self) -> Iterator[CardDefinition]:
        return iter(self._cards.values())

    def __len__(self) -> int:
        return len(self._cards)
