"""Smoke + property tests for the engine end-to-end milestone."""
import pytest
import random
from hypothesis import given, settings, strategies as st
from engine.card_db import CardDB
from engine.ruleset import RULESETS
from engine.deck import load_official_deck
from engine.setup import build_initial_state
from engine.step import step
from engine.bots.random_bot import random_legal_action
from engine.game_state import (
    Phase, PlayerID, validate_invariants, GameState,
)


@pytest.fixture(scope="module")
def db():
    return CardDB()


@pytest.fixture(scope="module")
def ruleset():
    return RULESETS["ST01-ST04-v1"]


def _run_full_game(seed: int, db, ruleset) -> GameState:
    p1_deck = load_official_deck("ST-01", db)
    p2_deck = load_official_deck("ST-02", db)
    state = build_initial_state(p1_deck, p2_deck, seed=seed, ruleset=ruleset, db=db)
    bot_rng = random.Random(seed + 100_000)
    while not state.is_terminal():
        action = random_legal_action(state, bot_rng, db)
        state = step(state, action, db)
        assert state.turn_number < 500, f"runaway at seed={seed}"
    return state


def test_smoke_random_game(db, ruleset):
    state = _run_full_game(42, db, ruleset)
    assert state.winner in (PlayerID.P1, PlayerID.P2)
    assert state.win_reason is not None


@given(seed=st.integers(0, 1000))
@settings(max_examples=100, deadline=None)
def test_termination_and_invariants(seed, db, ruleset):
    p1_deck = load_official_deck("ST-01", db)
    p2_deck = load_official_deck("ST-02", db)
    state = build_initial_state(p1_deck, p2_deck, seed=seed, ruleset=ruleset, db=db)
    bot_rng = random.Random(seed + 100_000)
    while not state.is_terminal():
        action = random_legal_action(state, bot_rng, db)
        state = step(state, action, db)
        validate_invariants(state)
        assert state.turn_number < 500, f"runaway at seed={seed}"
    assert state.winner is not None
    assert state.win_reason is not None


@given(seed=st.integers(0, 1000))
@settings(max_examples=50, deadline=None)
def test_determinism(seed, db, ruleset):
    a = _run_full_game(seed, db, ruleset)
    b = _run_full_game(seed, db, ruleset)
    assert a == b


@given(seed=st.integers(0, 1000))
@settings(max_examples=50, deadline=None)
def test_card_count_conserved(seed, db, ruleset):
    p1_deck = load_official_deck("ST-01", db)
    p2_deck = load_official_deck("ST-02", db)
    state = build_initial_state(p1_deck, p2_deck, seed=seed, ruleset=ruleset, db=db)
    bot_rng = random.Random(seed + 100_000)
    while not state.is_terminal():
        action = random_legal_action(state, bot_rng, db)
        state = step(state, action, db)
        assert len(state.p1.all_cards()) == 51
        assert len(state.p2.all_cards()) == 51
