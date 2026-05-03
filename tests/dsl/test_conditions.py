import dataclasses
import pytest
from engine.card_db import CardDB
from engine.game_state import PlayerID, DonField
from engine.dsl.conditions import evaluate
from tests.test_game_state import make_state


@pytest.fixture(scope="module")
def db():
    return CardDB()


def test_don_count_ge(db):
    state = make_state()
    p1 = dataclasses.replace(state.p1, don_field=DonField(active=3, rested=2))
    state = dataclasses.replace(state, p1=p1)
    assert evaluate({"type": "DonCount", "op": "ge", "value": 5},
                    state, source_controller=PlayerID.P1, db=db)
    assert not evaluate({"type": "DonCount", "op": "ge", "value": 6},
                        state, source_controller=PlayerID.P1, db=db)


def test_life_count_le(db):
    state = make_state()
    assert evaluate({"type": "LifeCount", "op": "le", "value": 5},
                    state, source_controller=PlayerID.P1, db=db)


def test_hand_count_eq(db):
    state = make_state()
    assert evaluate({"type": "HandCount", "op": "eq", "value": 0},
                    state, source_controller=PlayerID.P1, db=db)


def test_controller_has_filter_match(db):
    state = make_state()
    cond = {"type": "ControllerHas", "filter": {"type": "Leader"}, "op": "ge", "value": 1}
    assert evaluate(cond, state, source_controller=PlayerID.P1, db=db)


def test_source_attached_don(db):
    from engine.game_state import Zone
    from tests.test_game_state import make_card
    state = make_state()
    boosted = dataclasses.replace(state.p1.leader, attached_don=2)
    state = dataclasses.replace(state, p1=dataclasses.replace(state.p1, leader=boosted))
    cond = {"type": "SourceAttachedDon", "op": "ge", "value": 1}
    assert evaluate(cond, state, source_controller=PlayerID.P1, db=db, source_id="p1-leader")
    cond2 = {"type": "SourceAttachedDon", "op": "ge", "value": 5}
    assert not evaluate(cond2, state, source_controller=PlayerID.P1, db=db, source_id="p1-leader")


def test_unknown_condition_raises(db):
    with pytest.raises(ValueError, match="Unknown condition"):
        evaluate({"type": "Bogus"}, make_state(), source_controller=PlayerID.P1, db=db)
