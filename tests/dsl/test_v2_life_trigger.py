import dataclasses
import pytest
from engine.card_db import CardDB
from engine.game_state import Phase, PlayerID, Zone, BattleContext
from engine.actions import AdvancePhase, ActivateTrigger, PassTrigger
from engine.step import step
from engine.combat import _apply_leader_damage
from tests.test_game_state import make_state, make_card


@pytest.fixture
def db():
    return CardDB()


def _setup_life_trigger_state(state, db, monkeypatch, life_card_def="ST01-002",
                               trigger_effect=None, life_card_type=None):
    """P2 has 1 life card with a [Trigger]; phase = BATTLE_DAMAGE; battle_context set."""
    if trigger_effect is None:
        trigger_effect = {"type": "Draw", "count": 2}
    life_card = make_card("p2-life-0", life_card_def, Zone.LIFE, PlayerID.P2)
    state = dataclasses.replace(state, p2=dataclasses.replace(state.p2, life=(life_card,)),
                                battle_context=BattleContext(
                                    attacker_id="p1-leader", target_id="p2-leader"))
    triggers = ({"on": "Trigger", "effect": trigger_effect},)
    base = db._cards[life_card_def]
    if life_card_type is not None:
        base = dataclasses.replace(base, type=life_card_type)
    monkeypatch.setitem(db._cards, life_card_def,
                        dataclasses.replace(base, triggers=triggers, dsl_status="parsed"))
    return state


def test_apply_damage_pauses_at_trigger(db, monkeypatch):
    state = make_state(turn_number=2, phase=Phase.BATTLE_DAMAGE,
                       active_player_id=PlayerID.P1)
    state = _setup_life_trigger_state(state, db, monkeypatch)
    # Apply 1 damage; should pause at BATTLE_TRIGGER
    new_state = _apply_leader_damage(state, PlayerID.P2, damage=1, banish=False, db=db)
    assert new_state.phase == Phase.BATTLE_TRIGGER
    assert new_state.battle_context.pending_trigger_damage == 1
    # Life card still in life zone (not yet moved)
    assert len(new_state.p2.life) == 1


def test_pass_trigger_sends_card_to_hand(db, monkeypatch):
    state = make_state(turn_number=2, phase=Phase.BATTLE_TRIGGER,
                       active_player_id=PlayerID.P1)
    state = _setup_life_trigger_state(state, db, monkeypatch)
    state = dataclasses.replace(state, battle_context=dataclasses.replace(
        state.battle_context, pending_trigger_damage=1))
    pre_hand = len(state.p2.hand)
    new_state = step(state, PassTrigger(), db)
    assert any(c.instance_id == "p2-life-0" for c in new_state.p2.hand)
    assert len(new_state.p2.hand) == pre_hand + 1
    assert new_state.phase == Phase.BATTLE_CLEANUP


def test_activate_trigger_runs_effect_and_places_character_to_field(db, monkeypatch):
    state = make_state(turn_number=2, phase=Phase.BATTLE_TRIGGER,
                       active_player_id=PlayerID.P1)
    state = _setup_life_trigger_state(state, db, monkeypatch,
                                      trigger_effect={"type": "Draw", "count": 2})
    state = dataclasses.replace(state, battle_context=dataclasses.replace(
        state.battle_context, pending_trigger_damage=1))
    pre_hand = len(state.p2.hand)
    new_state = step(state, ActivateTrigger(), db)
    # Card (Character ST01-002) should be on P2's field, not in hand
    assert any(c.instance_id == "p2-life-0" for c in new_state.p2.field)
    # Effect (Draw 2) ran
    assert len(new_state.p2.hand) == pre_hand + 2


def test_activate_trigger_event_card_goes_to_trash(db, monkeypatch):
    state = make_state(turn_number=2, phase=Phase.BATTLE_TRIGGER,
                       active_player_id=PlayerID.P1)
    state = _setup_life_trigger_state(state, db, monkeypatch,
                                      trigger_effect={"type": "Draw", "count": 1},
                                      life_card_type="Event")
    state = dataclasses.replace(state, battle_context=dataclasses.replace(
        state.battle_context, pending_trigger_damage=1))
    pre_hand = len(state.p2.hand)
    new_state = step(state, ActivateTrigger(), db)
    # Card should be in trash (Event type)
    assert any(c.instance_id == "p2-life-0" for c in new_state.p2.trash)
    # Effect (Draw 1) ran
    assert len(new_state.p2.hand) == pre_hand + 1


def test_banish_skips_trigger(db, monkeypatch):
    """When attacker has Banish keyword, life card → trash and Trigger doesn't fire."""
    state = make_state(turn_number=2, phase=Phase.BATTLE_DAMAGE,
                       active_player_id=PlayerID.P1)
    state = _setup_life_trigger_state(state, db, monkeypatch)
    new_state = _apply_leader_damage(state, PlayerID.P2, damage=1, banish=True, db=db)
    # Banished: card to trash, no Trigger phase
    assert new_state.phase != Phase.BATTLE_TRIGGER
    assert any(c.instance_id == "p2-life-0" for c in new_state.p2.trash)
