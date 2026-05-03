import dataclasses
import pytest
from engine.card_db import CardDB
from engine.game_state import Phase, PlayerID, Zone
from engine.actions import AdvancePhase
from engine.step import step
from tests.test_game_state import make_state, make_card


@pytest.fixture
def db():
    return CardDB()


def test_end_of_your_turn_trigger_fires_during_end_phase(db, monkeypatch):
    state = make_state(turn_number=2, phase=Phase.END, active_player_id=PlayerID.P1)
    char = make_card("p1-c1", "ST01-002", Zone.FIELD, PlayerID.P1)
    state = dataclasses.replace(state, p1=dataclasses.replace(state.p1, field=(char,)))
    triggers = ({"on": "EndOfYourTurn", "effect": {"type": "Draw", "count": 1}},)
    monkeypatch.setitem(db._cards, "ST01-002",
                        dataclasses.replace(db._cards["ST01-002"], triggers=triggers,
                                            dsl_status="parsed"))
    pre_hand = len(state.p1.hand)
    new_state = step(state, AdvancePhase(), db)
    # Trigger fired (drew 1) and turn flipped
    assert len(new_state.p1.hand) == pre_hand + 1
    assert new_state.active_player_id == PlayerID.P2


def test_at_start_of_your_turn_trigger_fires_in_refresh(db, monkeypatch):
    state = make_state(turn_number=3, phase=Phase.REFRESH, active_player_id=PlayerID.P1)
    char = make_card("p1-c1", "ST01-002", Zone.FIELD, PlayerID.P1)
    state = dataclasses.replace(state, p1=dataclasses.replace(state.p1, field=(char,)))
    triggers = ({"on": "AtStartOfYourTurn", "effect": {"type": "Draw", "count": 1}},)
    monkeypatch.setitem(db._cards, "ST01-002",
                        dataclasses.replace(db._cards["ST01-002"], triggers=triggers,
                                            dsl_status="parsed"))
    pre_hand = len(state.p1.hand)
    new_state = step(state, AdvancePhase(), db)
    # After REFRESH, trigger drew 1; phase moved to DRAW
    assert len(new_state.p1.hand) == pre_hand + 1
    assert new_state.phase == Phase.DRAW


def test_no_trigger_no_change(db):
    """If no EndOfYourTurn cards, just turn flip happens."""
    state = make_state(turn_number=2, phase=Phase.END, active_player_id=PlayerID.P1)
    new_state = step(state, AdvancePhase(), db)
    assert new_state.active_player_id == PlayerID.P2
    assert new_state.turn_number == 3
