import dataclasses
import pytest
from engine.card_db import CardDB
from engine.game_state import ScopedEffect, Phase, PlayerID, Zone
from engine.actions import AdvancePhase
from engine.step import step
from tests.test_game_state import make_state, make_card


@pytest.fixture
def db():
    return CardDB()


def test_prevent_refresh_keeps_card_rested(db):
    state = make_state(turn_number=3, phase=Phase.REFRESH, active_player_id=PlayerID.P1)
    char = dataclasses.replace(
        make_card("p1-c1", "ST01-005", Zone.FIELD, PlayerID.P1),
        rested=True,
    )
    state = dataclasses.replace(state, p1=dataclasses.replace(state.p1, field=(char,)),
                                scoped_effects=(
        ScopedEffect(target_instance_id="p1-c1",
                     modification={"type": "PreventRefresh"}),
    ))
    state = step(state, AdvancePhase(), db)
    assert state.get_card("p1-c1").rested is True


def test_no_prevent_refresh_card_unrests(db):
    state = make_state(turn_number=3, phase=Phase.REFRESH, active_player_id=PlayerID.P1)
    char = dataclasses.replace(
        make_card("p1-c1", "ST01-005", Zone.FIELD, PlayerID.P1),
        rested=True,
    )
    state = dataclasses.replace(state, p1=dataclasses.replace(state.p1, field=(char,)))
    state = step(state, AdvancePhase(), db)
    assert state.get_card("p1-c1").rested is False
