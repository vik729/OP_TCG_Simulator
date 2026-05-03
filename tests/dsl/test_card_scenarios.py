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


def test_st01_006_loads_as_vanilla(db):
    cdef = db.get("ST01-006")
    assert cdef.dsl_status == "vanilla"
    assert cdef.triggers == ()
    assert "Blocker" in (cdef.keywords or ())


def test_st01_011_brook_attaches_two_rested_don_to_chosen_target(db):
    """Brook: [On Play] Give up to 2 rested DON to your Leader or 1 of your Characters."""
    state = make_state(turn_number=2)
    brook = make_card("p1-h0", "ST01-011", Zone.HAND, PlayerID.P1)
    p1 = dataclasses.replace(state.p1, hand=(brook,),
                             don_field=DonField(active=5, rested=0))
    state = dataclasses.replace(state, p1=p1)

    # Play Brook (cost 2)
    state = step(state, PlayCard(card_instance_id="p1-h0"), db)
    # OnPlay should pause for the AttachDon target choice
    assert state.pending_input is not None
    assert "p1-leader" in state.pending_input.valid_choices

    state = step(state, RespondInput(choices=("p1-leader",)), db)
    assert state.pending_input is None
    # Leader gained 2 attached DON, source took them from rested pool
    assert state.p1.leader.attached_don == 2


def test_st02_005_killer_kos_opponent_rested_low_cost_char(db):
    """Killer: [On Play] KO up to 1 opponent rested Character cost <= 3."""
    state = make_state(turn_number=2, active_player_id=PlayerID.P2)

    p1_char = dataclasses.replace(
        make_card("p1-c1", "ST01-002", Zone.FIELD, PlayerID.P1),
        rested=True,
    )
    new_p1 = dataclasses.replace(state.p1, field=(p1_char,))
    killer = make_card("p2-h0", "ST02-005", Zone.HAND, PlayerID.P2)
    p2 = dataclasses.replace(state.p2, hand=(killer,),
                             don_field=DonField(active=3, rested=0))
    state = dataclasses.replace(state, p1=new_p1, p2=p2)

    state = step(state, PlayCard(card_instance_id="p2-h0"), db)
    assert state.pending_input is not None
    assert "p1-c1" in state.pending_input.valid_choices

    state = step(state, RespondInput(choices=("p1-c1",)), db)
    assert state.pending_input is None
    assert all(c.instance_id != "p1-c1" for c in state.p1.field)
    assert any(c.instance_id == "p1-c1" for c in state.p1.trash)


def test_st01_005_jinbe_when_attacking_with_don_buffs_ally(db):
    """Jinbe: [DON!! x1][When Attacking] +1000 to a Leader/Character (not this one)."""
    state = make_state(turn_number=2)
    jinbe = dataclasses.replace(
        make_card("p1-jinbe", "ST01-005", Zone.FIELD, PlayerID.P1),
        attached_don=1,
    )
    target = make_card("p1-target", "ST01-002", Zone.FIELD, PlayerID.P1)
    p1 = dataclasses.replace(state.p1, field=(jinbe, target))
    state = dataclasses.replace(state, p1=p1)

    state = step(state, DeclareAttack(
        attacker_instance_id="p1-jinbe",
        target_instance_id="p2-leader"), db)

    assert state.pending_input is not None
    state = step(state, RespondInput(choices=("p1-target",)), db)

    matching = [se for se in state.scoped_effects
                if se.target_instance_id == "p1-target"
                and se.modification.get("type") == "PowerMod"]
    assert len(matching) == 1
    assert matching[0].modification["amount"] == 1000
    assert matching[0].expires_at == "END_TURN"


def test_st01_014_guard_point_counter_buffs_target_for_battle(db):
    """Guard Point: [Counter] +3000 to a Leader/Character this battle."""
    state = make_state(turn_number=2, phase=Phase.BATTLE_COUNTER,
                       active_player_id=PlayerID.P2)
    state = dataclasses.replace(state, battle_context=BattleContext(
        attacker_id="p2-leader", target_id="p1-leader", power_boosts=()))

    gp = make_card("p1-h0", "ST01-014", Zone.HAND, PlayerID.P1)
    p1 = dataclasses.replace(state.p1, hand=(gp,))
    state = dataclasses.replace(state, p1=p1)

    state = step(state, PlayCounter(card_instance_id="p1-h0"), db)
    assert state.pending_input is not None
    state = step(state, RespondInput(choices=("p1-leader",)), db)

    matching = [se for se in state.scoped_effects
                if se.target_instance_id == "p1-leader"
                and se.modification.get("type") == "PowerMod"]
    assert len(matching) == 1
    assert matching[0].modification["amount"] == 3000
    assert matching[0].expires_at == "BATTLE_CLEANUP"


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
