"""Tests for engine/step.py - the top-level step() dispatcher."""
import pytest
from engine.card_db import CardDB
from engine.deck import load_official_deck
from engine.ruleset import RULESETS
from engine.setup import build_initial_state
from engine.step import step, IllegalActionError
from engine.actions import (
    ChooseFirst, AdvancePhase, EndTurn, RespondInput,
)
from engine.game_state import Phase, PlayerID


@pytest.fixture(scope="module")
def db():
    return CardDB()


@pytest.fixture(scope="module")
def ruleset():
    return RULESETS["ST01-ST04-v1"]


@pytest.fixture
def setup_state(db, ruleset):
    st01 = load_official_deck("ST-01", db)
    st02 = load_official_deck("ST-02", db)
    return build_initial_state(st01, st02, seed=42, ruleset=ruleset, db=db)


class TestStep:
    def test_choose_first_dispatches(self, setup_state, db):
        new_state = step(setup_state, ChooseFirst("P1"), db)
        assert new_state.active_player_id == PlayerID.P1
        assert new_state.is_waiting_for_input()

    def test_illegal_action_raises(self, setup_state, db):
        with pytest.raises(IllegalActionError):
            step(setup_state, EndTurn(), db)

    def test_respond_when_pending_required(self, setup_state, db):
        s = step(setup_state, ChooseFirst("P1"), db)
        with pytest.raises(IllegalActionError):
            step(s, EndTurn(), db)

    def test_full_setup_to_main(self, setup_state, db):
        """ChooseFirst -> P1 mulligan no -> P2 mulligan no -> REFRESH."""
        s = step(setup_state, ChooseFirst("P1"), db)
        s = step(s, RespondInput(("no",)), db)
        s = step(s, RespondInput(("no",)), db)
        assert s.phase == Phase.REFRESH
        assert s.turn_number == 1

    def test_advance_through_turn_1_phases(self, setup_state, db):
        s = step(setup_state, ChooseFirst("P1"), db)
        s = step(s, RespondInput(("no",)), db)
        s = step(s, RespondInput(("no",)), db)
        s = step(s, AdvancePhase(), db)
        assert s.phase == Phase.DRAW
        s = step(s, AdvancePhase(), db)
        assert s.phase == Phase.DON
        s = step(s, AdvancePhase(), db)
        assert s.phase == Phase.MAIN
        # P1 should have 1 DON in cost area
        assert s.p1.don_field.active == 1
