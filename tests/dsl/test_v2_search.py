import dataclasses
import pytest
from engine.card_db import CardDB
from engine.game_state import PlayerID, Zone
from engine.dsl.operators import apply
from tests.test_game_state import make_state, make_card


@pytest.fixture
def db():
    return CardDB()


def test_search_deck_pauses_for_choice(db):
    state = make_state()
    node = {"type": "SearchDeck", "count": 3, "add_to_hand_max": 1,
            "remainder": "bottom_of_deck"}
    s2, req, _ = apply(node, state, source_controller=PlayerID.P1, db=db,
                       source_id=None, inputs=(), choice_index=0)
    assert req is not None
    assert len(req.valid_choices) == 3


def test_search_deck_remainder_bottom_of_deck(db):
    state = make_state()
    pre_deck_size = len(state.p1.deck)
    top_3 = tuple(c.instance_id for c in state.p1.deck[:3])
    chosen = top_3[0]
    node = {"type": "SearchDeck", "count": 3, "add_to_hand_max": 1,
            "remainder": "bottom_of_deck"}
    s3, req, _ = apply(node, state, source_controller=PlayerID.P1, db=db,
                       source_id=None, inputs=((chosen,),), choice_index=0)
    assert req is None
    assert any(c.instance_id == chosen for c in s3.p1.hand)
    assert s3.p1.deck[-2].instance_id == top_3[1]
    assert s3.p1.deck[-1].instance_id == top_3[2]
    assert len(s3.p1.deck) == pre_deck_size - 1


def test_search_deck_remainder_trash(db):
    state = make_state()
    top_3 = tuple(c.instance_id for c in state.p1.deck[:3])
    chosen = top_3[0]
    node = {"type": "SearchDeck", "count": 3, "add_to_hand_max": 1,
            "remainder": "trash"}
    s3, _, _ = apply(node, state, source_controller=PlayerID.P1, db=db,
                     source_id=None, inputs=((chosen,),), choice_index=0)
    trash_ids = {c.instance_id for c in s3.p1.trash}
    assert top_3[1] in trash_ids
    assert top_3[2] in trash_ids
    assert chosen not in trash_ids


def test_search_trash_picks_to_hand(db):
    state = make_state()
    t1 = make_card("p1-t1", "ST01-002", Zone.TRASH, PlayerID.P1)
    t2 = make_card("p1-t2", "ST01-002", Zone.TRASH, PlayerID.P1)
    state = dataclasses.replace(state, p1=dataclasses.replace(state.p1, trash=(t1, t2)))
    node = {"type": "SearchTrash", "filter": {"type": "Character"}, "add_to_hand_max": 1}
    s2, req, _ = apply(node, state, source_controller=PlayerID.P1, db=db,
                       source_id=None, inputs=(("p1-t1",),), choice_index=0)
    assert req is None
    assert any(c.instance_id == "p1-t1" for c in s2.p1.hand)
    assert all(c.instance_id != "p1-t1" for c in s2.p1.trash)


def test_rest_sets_target_to_rested(db):
    state = make_state()
    char = make_card("p2-c1", "ST01-002", Zone.FIELD, PlayerID.P2)
    state = dataclasses.replace(state, p2=dataclasses.replace(state.p2, field=(char,)))
    node = {"type": "Rest",
            "target": {"controller": "opponent", "type": "Character"},
            "max_choices": 1}
    s2, _, _ = apply(node, state, source_controller=PlayerID.P1, db=db,
                     source_id=None, inputs=(("p2-c1",),), choice_index=0)
    assert s2.get_card("p2-c1").rested is True
