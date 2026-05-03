import dataclasses
import pytest
from engine.card_db import CardDB
from engine.game_state import PlayerID, Zone
from engine.dsl.trigger_queue import find_triggers_for_event
from tests.test_game_state import make_state, make_card


@pytest.fixture
def db():
    return CardDB()


def test_find_triggers_returns_empty_when_no_matches(db):
    state = make_state()
    assert find_triggers_for_event(state, "EndOfYourTurn", PlayerID.P1, db) == []


def test_find_triggers_finds_matching_event_on_field(db, monkeypatch):
    state = make_state()
    char = make_card("p1-c1", "ST01-002", Zone.FIELD, PlayerID.P1)
    state = dataclasses.replace(state, p1=dataclasses.replace(state.p1, field=(char,)))
    triggers = ({"on": "EndOfYourTurn", "effect": {"type": "Draw", "count": 1}},)
    monkeypatch.setitem(db._cards, "ST01-002",
                        dataclasses.replace(db._cards["ST01-002"], triggers=triggers))
    found = find_triggers_for_event(state, "EndOfYourTurn", PlayerID.P1, db)
    assert len(found) == 1
    assert found[0][0].instance_id == "p1-c1"


def test_find_triggers_filters_by_controller(db, monkeypatch):
    state = make_state()
    p1_char = make_card("p1-c1", "ST01-002", Zone.FIELD, PlayerID.P1)
    p2_char = make_card("p2-c1", "ST01-002", Zone.FIELD, PlayerID.P2)
    state = dataclasses.replace(state,
        p1=dataclasses.replace(state.p1, field=(p1_char,)),
        p2=dataclasses.replace(state.p2, field=(p2_char,)))
    triggers = ({"on": "EndOfYourTurn", "effect": {"type": "Draw", "count": 1}},)
    monkeypatch.setitem(db._cards, "ST01-002",
                        dataclasses.replace(db._cards["ST01-002"], triggers=triggers))
    found = find_triggers_for_event(state, "EndOfYourTurn", PlayerID.P1, db)
    assert all(card.controller == PlayerID.P1 for card, _ in found)
