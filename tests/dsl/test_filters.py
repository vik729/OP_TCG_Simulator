import pytest
from engine.card_db import CardDB
from engine.game_state import PlayerID, Zone
from engine.dsl.filters import matches, find_targets
from tests.test_game_state import make_state, make_card


@pytest.fixture(scope="module")
def db():
    return CardDB()


def test_filter_controller_own(db):
    state = make_state()
    p1_card = state.p1.leader
    assert matches(p1_card, {"controller": "own"}, state, source_controller=PlayerID.P1, db=db)
    assert not matches(p1_card, {"controller": "own"}, state, source_controller=PlayerID.P2, db=db)


def test_filter_controller_opponent(db):
    state = make_state()
    p2_leader = state.p2.leader
    assert matches(p2_leader, {"controller": "opponent"}, state, source_controller=PlayerID.P1, db=db)
    assert not matches(p2_leader, {"controller": "opponent"}, state, source_controller=PlayerID.P2, db=db)


def test_filter_type_leader(db):
    state = make_state()
    leader = state.p1.leader
    assert matches(leader, {"type": "Leader"}, state, source_controller=PlayerID.P1, db=db)
    assert not matches(leader, {"type": "Character"}, state, source_controller=PlayerID.P1, db=db)


def test_filter_type_list_or_match(db):
    state = make_state()
    leader = state.p1.leader
    assert matches(leader, {"type": ["Leader", "Character"]}, state,
                   source_controller=PlayerID.P1, db=db)


def test_filter_power_le(db):
    state = make_state()
    leader = state.p1.leader
    assert matches(leader, {"power_le": 5000}, state, source_controller=PlayerID.P1, db=db)
    assert matches(leader, {"power_le": 6000}, state, source_controller=PlayerID.P1, db=db)
    assert not matches(leader, {"power_le": 4000}, state, source_controller=PlayerID.P1, db=db)


def test_filter_this_card(db):
    state = make_state()
    leader = state.p1.leader
    assert matches(leader, {"this_card": True}, state,
                   source_controller=PlayerID.P1, db=db, source_id="p1-leader")
    other_card = make_card("p1-other", "ST01-002", Zone.FIELD, PlayerID.P1)
    assert not matches(other_card, {"this_card": True}, state,
                       source_controller=PlayerID.P1, db=db, source_id="p1-leader")


def test_filter_not_this_card(db):
    state = make_state()
    leader = state.p1.leader
    assert not matches(leader, {"not_this_card": True}, state,
                       source_controller=PlayerID.P1, db=db, source_id="p1-leader")
    other_card = make_card("p1-other", "ST01-002", Zone.FIELD, PlayerID.P1)
    assert matches(other_card, {"not_this_card": True}, state,
                   source_controller=PlayerID.P1, db=db, source_id="p1-leader")


def test_find_targets_returns_leader(db):
    state = make_state()
    targets = find_targets({"controller": "own", "type": "Leader"},
                           state, source_controller=PlayerID.P1, db=db)
    assert "p1-leader" in [c.instance_id for c in targets]
