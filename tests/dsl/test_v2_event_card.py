import dataclasses
import pytest
from engine.card_db import CardDB
from engine.game_state import PlayerID, Zone, DonField
from engine.actions import PlayCard
from engine.step import step
from tests.test_game_state import make_state, make_card


@pytest.fixture
def db():
    return CardDB()


def test_event_card_goes_to_trash_after_play(db):
    """ST01-014 Guard Point is type=Event. Playing it should land it in trash, not field."""
    state = make_state(turn_number=2)
    event_card = make_card("p1-h0", "ST01-014", Zone.HAND, PlayerID.P1)
    p1 = dataclasses.replace(state.p1, hand=(event_card,),
                             don_field=DonField(active=1, rested=0))
    state = dataclasses.replace(state, p1=p1)
    state = step(state, PlayCard(card_instance_id="p1-h0"), db)
    assert all(c.instance_id != "p1-h0" for c in state.p1.field), "Event should not be on field"
    assert any(c.instance_id == "p1-h0" for c in state.p1.trash), "Event should be in trash"


def test_character_card_still_goes_to_field(db):
    """Sanity: Character cards still go to field after T7 changes."""
    state = make_state(turn_number=2)
    char = make_card("p1-h0", "ST01-002", Zone.HAND, PlayerID.P1)  # ST01-002 Usopp = Character
    p1 = dataclasses.replace(state.p1, hand=(char,),
                             don_field=DonField(active=2, rested=0))
    state = dataclasses.replace(state, p1=p1)
    state = step(state, PlayCard(card_instance_id="p1-h0"), db)
    assert any(c.instance_id == "p1-h0" for c in state.p1.field)
    assert all(c.instance_id != "p1-h0" for c in state.p1.trash)
