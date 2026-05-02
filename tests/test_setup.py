"""Tests for engine/setup.py - initial state + SETUP-phase action handlers."""
import pytest
from engine.card_db import CardDB
from engine.deck import load_official_deck
from engine.ruleset import RULESETS
from engine.setup import build_initial_state
from engine.game_state import (
    Phase, PlayerID, GameState, validate_invariants,
)


@pytest.fixture(scope="module")
def db():
    return CardDB()


@pytest.fixture(scope="module")
def ruleset():
    return RULESETS["ST01-ST04-v1"]


@pytest.fixture(scope="module")
def st01(db):
    return load_official_deck("ST-01", db)


@pytest.fixture(scope="module")
def st02(db):
    return load_official_deck("ST-02", db)


class TestBuildInitialState:
    def test_returns_setup_phase(self, db, ruleset, st01, st02):
        state = build_initial_state(st01, st02, seed=42, ruleset=ruleset, db=db)
        assert state.phase == Phase.SETUP

    def test_decks_loaded(self, db, ruleset, st01, st02):
        state = build_initial_state(st01, st02, seed=42, ruleset=ruleset, db=db)
        assert len(state.p1.deck) == 50
        assert len(state.p2.deck) == 50

    def test_leaders_set(self, db, ruleset, st01, st02):
        state = build_initial_state(st01, st02, seed=42, ruleset=ruleset, db=db)
        assert state.p1.leader.definition_id == st01.leader_id
        assert state.p2.leader.definition_id == st02.leader_id

    def test_no_hand_no_life_yet(self, db, ruleset, st01, st02):
        state = build_initial_state(st01, st02, seed=42, ruleset=ruleset, db=db)
        assert state.p1.hand == ()
        assert state.p1.life == ()
        assert state.p2.hand == ()
        assert state.p2.life == ()

    def test_don_decks_full(self, db, ruleset, st01, st02):
        state = build_initial_state(st01, st02, seed=42, ruleset=ruleset, db=db)
        assert state.p1.don_deck_count == 10
        assert state.p2.don_deck_count == 10
        assert state.p1.don_field.total == 0
        assert state.p2.don_field.total == 0

    def test_ruleset_id_stored(self, db, ruleset, st01, st02):
        state = build_initial_state(st01, st02, seed=42, ruleset=ruleset, db=db)
        assert state.ruleset_id == "ST01-ST04-v1"

    def test_passes_invariants(self, db, ruleset, st01, st02):
        state = build_initial_state(st01, st02, seed=42, ruleset=ruleset, db=db)
        validate_invariants(state)

    def test_unique_instance_ids(self, db, ruleset, st01, st02):
        state = build_initial_state(st01, st02, seed=42, ruleset=ruleset, db=db)
        all_ids = []
        for player in (state.p1, state.p2):
            for c in player.all_cards():
                all_ids.append(c.instance_id)
        assert len(all_ids) == len(set(all_ids))

    def test_fifty_one_cards_per_player(self, db, ruleset, st01, st02):
        state = build_initial_state(st01, st02, seed=42, ruleset=ruleset, db=db)
        assert len(state.p1.all_cards()) == 51
        assert len(state.p2.all_cards()) == 51

    def test_deterministic_with_same_seed(self, db, ruleset, st01, st02):
        a = build_initial_state(st01, st02, seed=42, ruleset=ruleset, db=db)
        b = build_initial_state(st01, st02, seed=42, ruleset=ruleset, db=db)
        assert a.p1.deck == b.p1.deck
        assert a.rng_state == b.rng_state


class TestSetupActionHandlers:
    def test_handler_module_imports(self):
        from engine.setup import handle_choose_first, handle_setup_respond_input
        assert callable(handle_choose_first)
        assert callable(handle_setup_respond_input)
