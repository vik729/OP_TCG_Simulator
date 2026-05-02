"""Tests for engine/bots/random_bot.py."""
import pytest
import random
from engine.card_db import CardDB
from engine.deck import load_official_deck
from engine.ruleset import RULESETS
from engine.setup import build_initial_state
from engine.bots.random_bot import random_legal_action, NoLegalActionsError
from engine.game_state import Phase, PlayerID, WinReason
from engine.actions import Action
from tests.test_game_state import make_state


@pytest.fixture(scope="module")
def db():
    return CardDB()


class TestRandomBot:
    def test_returns_legal_action(self, db):
        st01 = load_official_deck("ST-01", db)
        st02 = load_official_deck("ST-02", db)
        ruleset = RULESETS["ST01-ST04-v1"]
        state = build_initial_state(st01, st02, seed=42, ruleset=ruleset, db=db)
        rng = random.Random(7)
        action = random_legal_action(state, rng, db)
        assert isinstance(action, Action)

    def test_deterministic_with_same_seed(self, db):
        st01 = load_official_deck("ST-01", db)
        st02 = load_official_deck("ST-02", db)
        ruleset = RULESETS["ST01-ST04-v1"]
        state = build_initial_state(st01, st02, seed=42, ruleset=ruleset, db=db)
        rng_a = random.Random(7)
        rng_b = random.Random(7)
        actions_a = [random_legal_action(state, rng_a, db) for _ in range(5)]
        actions_b = [random_legal_action(state, rng_b, db) for _ in range(5)]
        assert actions_a == actions_b

    def test_no_legal_actions_raises(self, db):
        state = make_state(phase=Phase.GAME_OVER, winner=PlayerID.P1,
                           win_reason=WinReason.DECK_OUT)
        rng = random.Random(7)
        with pytest.raises(NoLegalActionsError):
            random_legal_action(state, rng, db)
