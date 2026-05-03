import dataclasses
import pytest
from engine.card_db import CardDB
from engine.game_state import ScopedEffect, PlayerID, Zone, DonField
from engine.actions import PlayCard
from engine.step import step
from tests.test_game_state import make_state, make_card


@pytest.fixture
def db():
    return CardDB()


def test_cost_reduction_lowers_play_cost(db):
    """A 2-cost card with -1 reduction can be played for 1 DON."""
    state = make_state(turn_number=2)
    card = make_card("p1-h0", "ST01-011", Zone.HAND, PlayerID.P1)  # cost 2
    state = dataclasses.replace(state, p1=dataclasses.replace(
        state.p1, hand=(card,), don_field=DonField(active=1, rested=0)),
        scoped_effects=(
            ScopedEffect(target_instance_id="p1-leader",
                         modification={"type": "CostReduction", "amount": -1}),
        ))
    # Should succeed despite only 1 DON
    state = step(state, PlayCard(card_instance_id="p1-h0"), db)
    assert any(c.instance_id == "p1-h0" for c in state.p1.field)


def test_cost_clamped_to_zero(db):
    """A 1-cost card with -3 reduction costs 0 DON."""
    state = make_state(turn_number=2)
    card = make_card("p1-h0", "ST01-007", Zone.HAND, PlayerID.P1)  # cost 1
    state = dataclasses.replace(state, p1=dataclasses.replace(
        state.p1, hand=(card,), don_field=DonField(active=0, rested=0)),
        scoped_effects=(
            ScopedEffect(target_instance_id="p1-leader",
                         modification={"type": "CostReduction", "amount": -3}),
        ))
    state = step(state, PlayCard(card_instance_id="p1-h0"), db)
    assert any(c.instance_id == "p1-h0" for c in state.p1.field)
