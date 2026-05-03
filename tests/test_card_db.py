"""Tests for engine/card_db.py — card definition loading."""
import pytest
from pathlib import Path
from engine.card_db import CardDB, CardDefinition, ConditionalKeywordGrant


@pytest.fixture(scope="module")
def db():
    return CardDB(cards_root=Path("cards"))


class TestLoad:
    def test_loads_st01_001(self, db):
        card = db.get("ST01-001")
        assert card.id == "ST01-001"
        assert card.name == "Monkey.D.Luffy (001)"
        assert card.type == "Leader"
        assert card.color == ("Red",)
        assert card.power == 5000
        assert card.life == 5
        assert card.attribute == "Strike"
        assert "Straw Hat Crew" in card.subtypes

    def test_loads_character_card(self, db):
        card = db.get("ST01-005")
        assert card.id == "ST01-005"
        assert card.type == "Character"
        assert card.cost == 3
        assert card.power == 5000
        assert card.counter == 0

    def test_unknown_card_raises(self, db):
        with pytest.raises(KeyError):
            db.get("XX99-999")

    def test_all_definitions_includes_st01_001(self, db):
        ids = [d.id for d in db.all_definitions()]
        assert "ST01-001" in ids

    def test_loads_all_st01_to_st04(self, db):
        ids = [d.id for d in db.all_definitions()]
        # ST01 has 17 cards, ST02-04 each have ~17. Total 68 per EFFECT_MAP.md.
        st01 = [i for i in ids if i.startswith("ST01-")]
        st02 = [i for i in ids if i.startswith("ST02-")]
        st03 = [i for i in ids if i.startswith("ST03-")]
        st04 = [i for i in ids if i.startswith("ST04-")]
        assert len(st01) > 0
        assert len(st02) > 0
        assert len(st03) > 0
        assert len(st04) > 0


class TestKeywords:
    def test_keywords_are_tuple(self, db):
        card = db.get("ST01-001")
        assert isinstance(card.keywords, tuple)

    def test_conditional_keywords_default_empty(self, db):
        card = db.get("ST01-001")
        assert card.conditional_keywords == ()

    def test_triggers_only_present_for_authored_cards(self, db):
        """Cards have triggers only if a YAML at cards/effects/<set>/<id>.yaml exists."""
        for card in db.all_definitions():
            if card.triggers:
                assert card.dsl_status == "parsed", \
                    f"{card.id} has triggers but dsl_status={card.dsl_status}"


class TestConditionalKeywordGrant:
    def test_construction(self):
        grant = ConditionalKeywordGrant(
            keyword="Rush",
            condition={"type": "don_attached_min", "value": 2},
        )
        assert grant.keyword == "Rush"
        assert grant.condition["value"] == 2
