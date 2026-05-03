import dataclasses
import pytest
from engine.card_db import CardDB
from engine.game_state import PlayerID, Zone, DonField
from engine.dsl.operators import apply
from tests.test_game_state import make_state, make_card


@pytest.fixture(scope="module")
def db():
    return CardDB()


def test_draw_moves_top_of_deck_to_hand(db):
    state = make_state()
    pre_hand = len(state.p1.hand)
    pre_deck = len(state.p1.deck)
    new_state, req, _ = apply({"type": "Draw", "count": 2}, state,
                              source_controller=PlayerID.P1, db=db, source_id=None,
                              inputs=(), choice_index=0)
    assert req is None
    assert len(new_state.p1.hand) == pre_hand + 2
    assert len(new_state.p1.deck) == pre_deck - 2


def test_ko_with_filter_targets_chosen_via_input(db):
    state = make_state()
    char = make_card("p2-c1", "ST01-002", Zone.FIELD, PlayerID.P2)
    new_p2 = dataclasses.replace(state.p2, field=(char,))
    state = dataclasses.replace(state, p2=new_p2)

    node = {"type": "KO", "target": {"controller": "opponent", "type": "Character"},
            "max_choices": 1}
    s2, req, idx = apply(node, state, source_controller=PlayerID.P1, db=db,
                         source_id=None, inputs=(), choice_index=0)
    assert req is not None
    assert "p2-c1" in req.valid_choices
    assert idx == 0

    s3, req2, idx2 = apply(node, state, source_controller=PlayerID.P1, db=db,
                           source_id=None, inputs=(("p2-c1",),), choice_index=0)
    assert req2 is None
    assert idx2 == 1
    assert len(s3.p2.field) == 0
    assert any(c.instance_id == "p2-c1" for c in s3.p2.trash)


def test_add_don_active(db):
    state = make_state()
    new_state, req, _ = apply({"type": "AddDon", "count": 2, "state": "active"},
                              state, source_controller=PlayerID.P1, db=db,
                              source_id=None, inputs=(), choice_index=0)
    assert req is None
    assert new_state.p1.don_field.active == 2
    assert new_state.p1.don_deck_count == 8


def test_attach_don_to_specific_target(db):
    state = make_state()
    p1 = dataclasses.replace(state.p1, don_field=DonField(active=2, rested=0))
    state = dataclasses.replace(state, p1=p1)
    node = {"type": "AttachDon", "target": {"this_card": True}, "count": 1, "state": "active"}
    new_state, req, _ = apply(node, state, source_controller=PlayerID.P1, db=db,
                              source_id="p1-leader", inputs=(("p1-leader",),), choice_index=0)
    assert req is None
    assert new_state.p1.leader.attached_don == 1
    assert new_state.p1.don_field.active == 1


def test_trash_hand_chooser_controller(db):
    state = make_state()
    card = make_card("p1-h1", "ST01-002", Zone.HAND, PlayerID.P1)
    p1 = dataclasses.replace(state.p1, hand=(card,))
    state = dataclasses.replace(state, p1=p1)
    node = {"type": "TrashHand", "count": 1, "chooser": "controller"}
    s2, req, _ = apply(node, state, source_controller=PlayerID.P1, db=db,
                       source_id=None, inputs=(), choice_index=0)
    assert req is not None
    assert "p1-h1" in req.valid_choices
    s3, _, _ = apply(node, state, source_controller=PlayerID.P1, db=db,
                     source_id=None, inputs=(("p1-h1",),), choice_index=0)
    assert len(s3.p1.hand) == 0
    assert any(c.instance_id == "p1-h1" for c in s3.p1.trash)


def test_bounce_returns_target_to_owner_hand(db):
    state = make_state()
    char = make_card("p2-c1", "ST01-002", Zone.FIELD, PlayerID.P2)
    new_p2 = dataclasses.replace(state.p2, field=(char,))
    state = dataclasses.replace(state, p2=new_p2)
    node = {"type": "Bounce", "target": {"controller": "opponent", "type": "Character"},
            "max_choices": 1}
    s2, req, _ = apply(node, state, source_controller=PlayerID.P1, db=db,
                       source_id=None, inputs=(("p2-c1",),), choice_index=0)
    assert req is None
    assert len(s2.p2.field) == 0
    assert any(c.instance_id == "p2-c1" for c in s2.p2.hand)


def test_give_power_appends_scoped_effect(db):
    state = make_state()
    node = {"type": "GivePower", "target": {"this_card": True},
            "amount": 2000, "until": "end_of_battle", "max_choices": 1}
    s2, req, _ = apply(node, state, source_controller=PlayerID.P1, db=db,
                       source_id="p1-leader", inputs=(("p1-leader",),), choice_index=0)
    assert req is None
    matching = [se for se in s2.scoped_effects
                if se.target_instance_id == "p1-leader"
                and se.modification.get("type") == "PowerMod"]
    assert len(matching) == 1
    assert matching[0].modification["amount"] == 2000
    assert matching[0].expires_at == "BATTLE_CLEANUP"


def test_give_power_until_end_of_turn(db):
    state = make_state()
    node = {"type": "GivePower", "target": {"this_card": True},
            "amount": -1000, "until": "end_of_this_turn", "max_choices": 1}
    s2, _, _ = apply(node, state, source_controller=PlayerID.P1, db=db,
                     source_id="p1-leader", inputs=(("p1-leader",),), choice_index=0)
    matching = [se for se in s2.scoped_effects if se.target_instance_id == "p1-leader"]
    assert matching[0].expires_at == "END_TURN"


def test_grant_keyword_appends_scoped_effect(db):
    state = make_state()
    node = {"type": "GrantKeyword", "target": {"this_card": True},
            "keyword": "Rush", "until": "end_of_this_turn", "max_choices": 1}
    s2, _, _ = apply(node, state, source_controller=PlayerID.P1, db=db,
                     source_id="p1-leader", inputs=(("p1-leader",),), choice_index=0)
    matching = [se for se in s2.scoped_effects
                if se.modification.get("type") == "KeywordGrant"]
    assert len(matching) == 1
    assert matching[0].modification["keyword"] == "Rush"
