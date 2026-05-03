"""End-to-end card scenario tests. Each test sets up a state where a card's
trigger should fire, runs step() with the appropriate action, and asserts the
engine resolved the effect."""
import dataclasses
import pytest
from engine.card_db import CardDB
from engine.game_state import (
    Phase, PlayerID, Zone, DonField, BattleContext,
)
from engine.actions import PlayCard, RespondInput, DeclareAttack, PlayCounter
from engine.step import step
from tests.test_game_state import make_state, make_card


@pytest.fixture
def db():
    return CardDB()


def test_play_card_with_on_play_draw_triggers_resolution(db, monkeypatch):
    """T14: A card with an OnPlay Draw trigger draws when played."""
    target_id = "ST01-002"
    original = db._cards[target_id]
    triggers = ({"on": "OnPlay", "effect": {"type": "Draw", "count": 1}},)
    monkeypatch.setitem(db._cards, target_id,
                        dataclasses.replace(original, triggers=triggers, dsl_status="parsed"))

    state = make_state(turn_number=2)
    card = make_card("p1-h0", target_id, Zone.HAND, PlayerID.P1)
    p1 = dataclasses.replace(state.p1, hand=(card,),
                             don_field=DonField(active=2, rested=0))
    state = dataclasses.replace(state, p1=p1)

    new_state = step(state, PlayCard(card_instance_id="p1-h0"), db)

    # Card moved to field, OnPlay drew 1 -> hand still has 1 card (the drawn one)
    assert len(new_state.p1.field) == 1
    assert len(new_state.p1.hand) == 1
