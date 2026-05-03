import dataclasses
import pytest
from engine.card_db import CardDB
from engine.game_state import PlayerID, DonField
from engine.dsl.operators import apply
from tests.test_game_state import make_state


@pytest.fixture(scope="module")
def db():
    return CardDB()


def test_sequence_runs_each_step_in_order(db):
    state = make_state()
    pre_hand = len(state.p1.hand)
    node = {"type": "Sequence", "steps": [
        {"type": "Draw", "count": 1},
        {"type": "Draw", "count": 2},
    ]}
    s2, req, _ = apply(node, state, source_controller=PlayerID.P1, db=db,
                       source_id=None, inputs=(), choice_index=0)
    assert req is None
    assert len(s2.p1.hand) == pre_hand + 3


def test_if_then_branch_when_condition_true(db):
    state = make_state()
    p1 = dataclasses.replace(state.p1, don_field=DonField(active=5, rested=0))
    state = dataclasses.replace(state, p1=p1)
    pre_hand = len(state.p1.hand)
    node = {"type": "If",
            "condition": {"type": "DonCount", "op": "ge", "value": 4},
            "then": {"type": "Draw", "count": 1}}
    s2, req, _ = apply(node, state, source_controller=PlayerID.P1, db=db,
                       source_id=None, inputs=(), choice_index=0)
    assert req is None
    assert len(s2.p1.hand) == pre_hand + 1


def test_if_else_branch_when_condition_false(db):
    state = make_state()
    pre_hand = len(state.p1.hand)
    node = {"type": "If",
            "condition": {"type": "DonCount", "op": "ge", "value": 99},
            "then": {"type": "Draw", "count": 99},
            "else": {"type": "Draw", "count": 1}}
    s2, req, _ = apply(node, state, source_controller=PlayerID.P1, db=db,
                       source_id=None, inputs=(), choice_index=0)
    assert req is None
    assert len(s2.p1.hand) == pre_hand + 1


def test_if_no_else_skips_when_condition_false(db):
    state = make_state()
    pre_hand = len(state.p1.hand)
    node = {"type": "If",
            "condition": {"type": "DonCount", "op": "ge", "value": 99},
            "then": {"type": "Draw", "count": 1}}
    s2, req, _ = apply(node, state, source_controller=PlayerID.P1, db=db,
                       source_id=None, inputs=(), choice_index=0)
    assert req is None
    assert len(s2.p1.hand) == pre_hand


def test_choice_pauses_for_yes_no(db):
    state = make_state()
    node = {"type": "Choice", "prompt": "Activate?",
            "effect": {"type": "Draw", "count": 1}}
    s2, req, _ = apply(node, state, source_controller=PlayerID.P1, db=db,
                       source_id=None, inputs=(), choice_index=0)
    assert req is not None
    assert req.request_type == "YesNo"

    pre_hand = len(state.p1.hand)
    s3, req3, _ = apply(node, state, source_controller=PlayerID.P1, db=db,
                        source_id=None, inputs=(("yes",),), choice_index=0)
    assert req3 is None
    assert len(s3.p1.hand) == pre_hand + 1

    s4, req4, _ = apply(node, state, source_controller=PlayerID.P1, db=db,
                        source_id=None, inputs=(("no",),), choice_index=0)
    assert req4 is None
    assert len(s4.p1.hand) == pre_hand
