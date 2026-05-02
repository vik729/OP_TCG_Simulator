"""Tests for engine/deck.py - deck loading and validation."""
import pytest
import yaml
from pathlib import Path
from engine.card_db import CardDB
from engine.deck import (
    DeckList, DeckValidationError,
    load_official_deck, load_custom_deck, validate_deck,
)
from engine.ruleset import Ruleset, RULESETS


@pytest.fixture(scope="module")
def db():
    return CardDB()


@pytest.fixture
def ruleset():
    return RULESETS["ST01-ST04-v1"]


class TestLoadOfficial:
    def test_load_st_01(self, db):
        deck = load_official_deck("ST-01", db)
        assert isinstance(deck, DeckList)
        assert deck.leader_id == "ST01-001"
        assert len(deck.main_deck_ids) == 50

    def test_load_st_02(self, db):
        deck = load_official_deck("ST-02", db)
        assert isinstance(deck, DeckList)
        assert len(deck.main_deck_ids) == 50

    def test_unknown_deck_raises(self, db):
        with pytest.raises(FileNotFoundError):
            load_official_deck("XX-99", db)


class TestLoadCustom:
    def test_load_custom(self, db, tmp_path):
        path = tmp_path / "test_deck.yaml"
        path.write_text(yaml.safe_dump({
            "leader": "ST01-001",
            "main_deck": [
                {"id": "ST01-002", "count": 4},
                {"id": "ST01-003", "count": 4},
                {"id": "ST01-004", "count": 4},
                {"id": "ST01-005", "count": 4},
                {"id": "ST01-006", "count": 4},
                {"id": "ST01-007", "count": 4},
                {"id": "ST01-008", "count": 4},
                {"id": "ST01-009", "count": 4},
                {"id": "ST01-010", "count": 4},
                {"id": "ST01-011", "count": 4},
                {"id": "ST01-012", "count": 4},
                {"id": "ST01-013", "count": 4},
                {"id": "ST01-014", "count": 2},
            ],
        }))
        deck = load_custom_deck(path, db)
        assert deck.leader_id == "ST01-001"
        assert len(deck.main_deck_ids) == 50


class TestValidate:
    def test_official_st_01_passes(self, db, ruleset):
        deck = load_official_deck("ST-01", db)
        validate_deck(deck, db, ruleset)

    def test_wrong_size_fails(self, db, ruleset):
        deck = DeckList(leader_id="ST01-001", main_deck_ids=("ST01-002",) * 49)
        with pytest.raises(DeckValidationError, match="50"):
            validate_deck(deck, db, ruleset)

    def test_too_many_copies_fails(self, db, ruleset):
        deck = DeckList(
            leader_id="ST01-001",
            main_deck_ids=("ST01-002",) * 5 + ("ST01-003",) * 45,
        )
        with pytest.raises(DeckValidationError, match="(?i)more than 4|max"):
            validate_deck(deck, db, ruleset)

    def test_wrong_color_fails(self, db, ruleset):
        non_red_card = None
        for d in db.all_definitions():
            if d.type == "Character" and "Red" not in d.color and d.color:
                non_red_card = d.id
                break
        assert non_red_card is not None, "test setup: no non-Red character found"
        deck = DeckList(
            leader_id="ST01-001",
            main_deck_ids=(non_red_card,) * 4 + ("ST01-002",) * 46,
        )
        with pytest.raises(DeckValidationError, match="(?i)color"):
            validate_deck(deck, db, ruleset)

    def test_unknown_card_fails(self, db, ruleset):
        deck = DeckList(
            leader_id="ST01-001",
            main_deck_ids=("XX99-999",) * 4 + ("ST01-002",) * 46,
        )
        with pytest.raises(DeckValidationError, match="(?i)unknown|not found"):
            validate_deck(deck, db, ruleset)

    def test_banned_card_fails(self, db):
        rs = Ruleset(id="test", banlist=frozenset({"ST01-002"}))
        deck = DeckList(
            leader_id="ST01-001",
            main_deck_ids=("ST01-002",) * 4 + ("ST01-003",) * 46,
        )
        with pytest.raises(DeckValidationError, match="(?i)ban"):
            validate_deck(deck, db, rs)

    def test_non_leader_as_leader_fails(self, db, ruleset):
        deck = DeckList(
            leader_id="ST01-002",
            main_deck_ids=("ST01-003",) * 50,
        )
        with pytest.raises(DeckValidationError, match="(?i)leader"):
            validate_deck(deck, db, ruleset)
