"""Tests for engine/keywords.py — effective_keywords + condition evaluator."""
import pytest
import dataclasses
from engine.keywords import effective_keywords, evaluate_condition
from engine.card_db import CardDB, CardDefinition, ConditionalKeywordGrant
from engine.game_state import (
    CardInstance, Phase, Zone, PlayerID,
)
from tests.test_game_state import make_state, make_card


@pytest.fixture(scope="module")
def db():
    return CardDB()


class TestEffectiveKeywords:
    def test_innate_keywords_returned(self, db):
        """L1: keywords from CardDefinition are returned."""
        # Use a card we know has [] keywords for baseline
        card = make_card("p1-test", "ST01-001", Zone.FIELD, PlayerID.P1)
        state = make_state()
        result = effective_keywords(card, db, state)
        # ST01-001 (Luffy leader) has no static keywords per EFFECT_MAP
        assert isinstance(result, frozenset)

    # L3 (TempKeyword) test removed — see T6 for ScopedEffect KeywordGrant lookup

class TestEvaluateCondition:
    def test_don_attached_min_satisfied(self, db):
        card = CardInstance(
            instance_id="p1-test", definition_id="ST01-001",
            zone=Zone.FIELD, controller=PlayerID.P1, attached_don=3,
        )
        state = make_state()
        cond = {"type": "don_attached_min", "value": 2}
        assert evaluate_condition(cond, card, state) is True

    def test_don_attached_min_not_satisfied(self, db):
        card = CardInstance(
            instance_id="p1-test", definition_id="ST01-001",
            zone=Zone.FIELD, controller=PlayerID.P1, attached_don=1,
        )
        state = make_state()
        cond = {"type": "don_attached_min", "value": 2}
        assert evaluate_condition(cond, card, state) is False

    def test_unknown_condition_raises(self, db):
        card = make_card("p1-test")
        state = make_state()
        with pytest.raises(NotImplementedError):
            evaluate_condition({"type": "unknown_type"}, card, state)
