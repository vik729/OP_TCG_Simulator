"""
engine/combat.py
================
Battle sub-phase state machine.

7 phases: BATTLE_DECLARED, BATTLE_WHEN_ATK, BATTLE_BLOCKER, BATTLE_COUNTER,
BATTLE_DAMAGE, BATTLE_TRIGGER, BATTLE_CLEANUP.

Vanilla simplifications:
  - BATTLE_WHEN_ATK has no triggers to fire - it's pure no-op transition.
  - BATTLE_TRIGGER is never entered (no card has parsed [Trigger]) - DAMAGE
    transitions directly to CLEANUP.
"""
from __future__ import annotations
import dataclasses
from typing import Optional
from engine.game_state import (
    GameState, Phase, PlayerID, CardInstance, Zone, BattleContext, DonField,
    WinReason,
)
from engine.actions import (
    DeclareAttack, DeclareBlocker, PassBlocker,
    PlayCounter, PassCounter,
    ActivateTrigger, PassTrigger, AdvancePhase,
)
from engine.card_db import CardDB
from engine.keywords import effective_keywords


def begin_attack(state: GameState, action: DeclareAttack, db: CardDB) -> GameState:
    """MAIN -> BATTLE_DECLARED. Rests the attacker, sets battle_context, fires WhenAttacking triggers."""
    attacker_id = action.attacker_instance_id
    target_id = action.target_instance_id

    attacker = state.get_card(attacker_id)
    if attacker is None:
        raise ValueError(f"Attacker {attacker_id} not found")
    new_state = _replace_card(state, attacker_id, dataclasses.replace(attacker, rested=True))

    ctx = BattleContext(attacker_id=attacker_id, target_id=target_id)
    new_state = dataclasses.replace(new_state, phase=Phase.BATTLE_DECLARED, battle_context=ctx)

    # Fire any WhenAttacking triggers on the attacker.
    atk_def = db.get(attacker.definition_id)
    when_atk_triggers = [t for t in (atk_def.triggers or []) if t.get("on") == "WhenAttacking"]
    if when_atk_triggers:
        from engine.game_state import StackEntry
        for trigger in when_atk_triggers:
            entry = StackEntry(
                effect=trigger["effect"],
                source_instance_id=attacker_id,
                controller=attacker.controller,
                inputs_collected=(),
                initial_state_ref=new_state,
            )
            new_state = dataclasses.replace(
                new_state, effect_stack=new_state.effect_stack + (entry,)
            )

    return new_state


def handle_blocker(state: GameState, action: DeclareBlocker, db: CardDB) -> GameState:
    assert state.battle_context is not None
    blocker_id = action.blocker_instance_id
    new_ctx = dataclasses.replace(state.battle_context, target_id=blocker_id)
    blocker = state.get_card(blocker_id)
    if blocker is not None:
        state = _replace_card(state, blocker_id, dataclasses.replace(blocker, rested=True))
    return dataclasses.replace(state, battle_context=new_ctx, phase=Phase.BATTLE_COUNTER)


def handle_pass_blocker(state: GameState, action: PassBlocker, db: CardDB) -> GameState:
    return dataclasses.replace(state, phase=Phase.BATTLE_COUNTER)


def handle_counter(state: GameState, action: PlayCounter, db: CardDB) -> GameState:
    """BATTLE_COUNTER: trash counter card, apply static counter value, fire any Counter triggers."""
    assert state.battle_context is not None
    card_id = action.card_instance_id
    card = state.get_card(card_id)
    if card is None:
        raise ValueError(f"Counter card {card_id} not found")
    cdef = db.get(card.definition_id)
    counter_value = cdef.counter or 0
    defender = state.inactive_player()
    new_hand = tuple(c for c in defender.hand if c.instance_id != card_id)
    new_trash = defender.trash + (dataclasses.replace(card, zone=Zone.TRASH),)
    new_defender = dataclasses.replace(defender, hand=new_hand, trash=new_trash)
    new_state = _replace_player(state, defender.player_id, new_defender)
    new_boosts = state.battle_context.power_boosts + (counter_value,)
    new_ctx = dataclasses.replace(state.battle_context, power_boosts=new_boosts)
    new_state = dataclasses.replace(new_state, battle_context=new_ctx)

    # Fire any Counter-window triggers on the played counter card.
    counter_triggers = [t for t in (cdef.triggers or []) if t.get("on") == "Counter"]
    if counter_triggers:
        from engine.game_state import StackEntry
        for trigger in counter_triggers:
            entry = StackEntry(
                effect=trigger["effect"],
                source_instance_id=card.instance_id,
                controller=defender.player_id,
                inputs_collected=(),
                initial_state_ref=new_state,
            )
            new_state = dataclasses.replace(
                new_state, effect_stack=new_state.effect_stack + (entry,)
            )

    return new_state


def handle_pass_counter(state: GameState, action: PassCounter, db: CardDB) -> GameState:
    return dataclasses.replace(state, phase=Phase.BATTLE_DAMAGE)


def handle_trigger(state: GameState, action: ActivateTrigger, db: CardDB) -> GameState:
    """v2: Defender activates the revealed life card's [Trigger].
    Card destination is dictated by its type:
      - Character -> Field (and OnPlay triggers fire)
      - Event     -> Trash (after effect)
      - Stage     -> Hand (deferred to v3)
    Then the trigger's effect is pushed onto effect_stack.
    Damage continues if remaining > 1."""
    assert state.battle_context is not None
    defender_id = _defender_from_context(state)
    defender = state.get_player(defender_id)
    if not defender.life:
        return dataclasses.replace(state, phase=Phase.BATTLE_CLEANUP)
    revealed = defender.life[0]
    cdef = db.get(revealed.definition_id)
    trigger = next((t for t in cdef.triggers if t.get("on") == "Trigger"), None)
    if trigger is None:
        # Defensive: shouldn't happen if pause condition was met
        return dataclasses.replace(state, phase=Phase.BATTLE_CLEANUP)

    new_life = defender.life[1:]
    if cdef.type == "Character":
        new_card = dataclasses.replace(revealed, zone=Zone.FIELD,
                                        rested=False, attached_don=0)
        new_defender = dataclasses.replace(defender, life=new_life,
                                           field=defender.field + (new_card,))
        new_state = _replace_player(state, defender_id, new_defender)
        # Push OnPlay triggers if any
        on_play = [t for t in cdef.triggers if t.get("on") == "OnPlay"]
        for op_t in on_play:
            new_state = _push_entry(new_state, op_t["effect"], revealed.instance_id, defender_id)
    elif cdef.type == "Event":
        new_card = dataclasses.replace(revealed, zone=Zone.TRASH)
        new_defender = dataclasses.replace(defender, life=new_life,
                                           trash=defender.trash + (new_card,))
        new_state = _replace_player(state, defender_id, new_defender)
    else:
        # Stage / fallback: send to hand
        new_card = dataclasses.replace(revealed, zone=Zone.HAND)
        new_defender = dataclasses.replace(defender, life=new_life,
                                           hand=defender.hand + (new_card,))
        new_state = _replace_player(state, defender_id, new_defender)

    new_state = _push_entry(new_state, trigger["effect"], revealed.instance_id, defender_id)

    # Continue with remaining damage
    remaining = state.battle_context.pending_trigger_damage - 1
    new_ctx = dataclasses.replace(new_state.battle_context, pending_trigger_damage=0)
    new_state = dataclasses.replace(new_state, battle_context=new_ctx)
    if remaining > 0:
        return _apply_leader_damage(new_state, defender_id, remaining, banish=False, db=db)
    return dataclasses.replace(new_state, phase=Phase.BATTLE_CLEANUP)


def handle_pass_trigger(state: GameState, action: PassTrigger, db: CardDB) -> GameState:
    """v2: Defender passes the trigger; revealed card goes to hand (default)."""
    assert state.battle_context is not None
    defender_id = _defender_from_context(state)
    defender = state.get_player(defender_id)
    if not defender.life:
        return dataclasses.replace(state, phase=Phase.BATTLE_CLEANUP)
    revealed = defender.life[0]
    new_card = dataclasses.replace(revealed, zone=Zone.HAND)
    new_defender = dataclasses.replace(
        defender, life=defender.life[1:], hand=defender.hand + (new_card,),
    )
    new_state = _replace_player(state, defender_id, new_defender)

    remaining = state.battle_context.pending_trigger_damage - 1
    new_ctx = dataclasses.replace(new_state.battle_context, pending_trigger_damage=0)
    new_state = dataclasses.replace(new_state, battle_context=new_ctx)
    if remaining > 0:
        return _apply_leader_damage(new_state, defender_id, remaining, banish=False, db=db)
    return dataclasses.replace(new_state, phase=Phase.BATTLE_CLEANUP)


def _defender_from_context(state: GameState) -> PlayerID:
    target = state.get_card(state.battle_context.target_id)
    if target is not None:
        return target.controller
    return state.active_player_id.opponent()


def _push_entry(state: GameState, effect: dict, source_id: str, controller: PlayerID) -> GameState:
    from engine.game_state import StackEntry
    entry = StackEntry(
        effect=effect, source_instance_id=source_id, controller=controller,
        inputs_collected=(), initial_state_ref=state,
    )
    return dataclasses.replace(state, effect_stack=state.effect_stack + (entry,))


def advance_battle(state: GameState, db: CardDB) -> GameState:
    """Handle AdvancePhase for any battle auto-phase."""
    if state.phase == Phase.BATTLE_DECLARED:
        return dataclasses.replace(state, phase=Phase.BATTLE_WHEN_ATK)
    if state.phase == Phase.BATTLE_WHEN_ATK:
        return dataclasses.replace(state, phase=Phase.BATTLE_BLOCKER)
    if state.phase == Phase.BATTLE_DAMAGE:
        return _do_damage(state, db)
    if state.phase == Phase.BATTLE_CLEANUP:
        return _do_cleanup(state, db)
    raise ValueError(f"advance_battle called in non-auto battle phase: {state.phase}")


def battle_power(card: CardInstance, cdef, state: GameState) -> int:
    """Card's power during battle. Per rule 6-5-5-2, attached DON only adds
    power during the controller's turn."""
    base = cdef.power or 0
    if card.controller == state.active_player_id:
        return base + 1000 * card.attached_don
    return base


def _do_damage(state: GameState, db: CardDB) -> GameState:
    """Compute powers, apply damage, transition to CLEANUP (vanilla skips TRIGGER)."""
    assert state.battle_context is not None
    attacker = state.get_card(state.battle_context.attacker_id)
    target = state.get_card(state.battle_context.target_id)
    if attacker is None or target is None:
        return dataclasses.replace(state, phase=Phase.BATTLE_CLEANUP)

    atk_def = db.get(attacker.definition_id)
    tgt_def = db.get(target.definition_id)
    atk_power = battle_power(attacker, atk_def, state)
    tgt_power = battle_power(target, tgt_def, state) + sum(state.battle_context.power_boosts)

    from engine.dsl.lookups import power_modifiers
    atk_power += power_modifiers(state, attacker.instance_id)
    tgt_power += power_modifiers(state, target.instance_id)

    if atk_power < tgt_power:
        return dataclasses.replace(state, phase=Phase.BATTLE_CLEANUP)

    if tgt_def.type == "Leader":
        damage = 1
        if "Double Attack" in effective_keywords(attacker, db, state):
            damage = 2
        new_state = _apply_leader_damage(
            state, target.controller, damage,
            banish=("Banish" in effective_keywords(attacker, db, state)),
            db=db,
        )
        if new_state.phase == Phase.GAME_OVER:
            return new_state
        return dataclasses.replace(new_state, phase=Phase.BATTLE_CLEANUP)
    else:
        new_state = _ko_character(state, target.instance_id, target.controller, db)
        return dataclasses.replace(new_state, phase=Phase.BATTLE_CLEANUP)


def _apply_leader_damage(state: GameState, leader_owner: PlayerID, damage: int,
                          banish: bool, db: CardDB) -> GameState:
    """Apply N damage to the leader. Each damage:
      - if life empty -> GAME_OVER (LIFE_AND_LEADER_HIT)
      - else if revealed card has [Trigger] AND not banish -> pause in
        BATTLE_TRIGGER; defender chooses Activate or Pass
      - else move life->trash (banish) or life->hand (default)"""
    new_state = state
    remaining = damage
    while remaining > 0:
        owner_state = new_state.get_player(leader_owner)
        if len(owner_state.life) == 0:
            return dataclasses.replace(
                new_state,
                phase=Phase.GAME_OVER,
                winner=leader_owner.opponent(),
                win_reason=WinReason.LIFE_AND_LEADER_HIT,
                battle_context=None,
            )
        top = owner_state.life[0]
        cdef = db.get(top.definition_id)
        has_trigger = any(t.get("on") == "Trigger" for t in (cdef.triggers or ()))
        if has_trigger and not banish:
            # Pause: defender chooses Activate or Pass.
            new_ctx = dataclasses.replace(
                new_state.battle_context, pending_trigger_damage=remaining,
            )
            return dataclasses.replace(
                new_state, phase=Phase.BATTLE_TRIGGER, battle_context=new_ctx,
            )
        # Default flow: move card without Trigger
        rest = owner_state.life[1:]
        if banish:
            new_top = dataclasses.replace(top, zone=Zone.TRASH)
            new_owner = dataclasses.replace(
                owner_state,
                life=rest,
                trash=owner_state.trash + (new_top,),
            )
        else:
            new_top = dataclasses.replace(top, zone=Zone.HAND)
            new_owner = dataclasses.replace(
                owner_state,
                life=rest,
                hand=owner_state.hand + (new_top,),
            )
        new_state = _replace_player(new_state, leader_owner, new_owner)
        remaining -= 1
    return new_state


def _ko_character(state: GameState, char_id: str, owner: PlayerID, db: CardDB) -> GameState:
    owner_state = state.get_player(owner)
    new_field = tuple(c for c in owner_state.field if c.instance_id != char_id)
    char = state.get_card(char_id)
    if char is None:
        return state
    new_trash = owner_state.trash + (dataclasses.replace(char, zone=Zone.TRASH, rested=False, attached_don=0),)
    don_to_return = char.attached_don
    new_don_field = DonField(
        active=owner_state.don_field.active,
        rested=owner_state.don_field.rested + don_to_return,
    )
    new_owner = dataclasses.replace(
        owner_state, field=new_field, trash=new_trash, don_field=new_don_field,
    )
    return _replace_player(state, owner, new_owner)


def _do_cleanup(state: GameState, db: CardDB) -> GameState:
    """Clear battle_context; remove temp effects with expires_after=BATTLE_CLEANUP."""
    new_scoped = tuple(
        se for se in state.scoped_effects if se.expires_at != "BATTLE_CLEANUP"
    )
    return dataclasses.replace(
        state, phase=Phase.MAIN, battle_context=None, scoped_effects=new_scoped,
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _replace_player(state: GameState, pid: PlayerID, new_player) -> GameState:
    if pid == PlayerID.P1:
        return dataclasses.replace(state, p1=new_player)
    return dataclasses.replace(state, p2=new_player)


def _replace_card(state: GameState, instance_id: str, new_card: CardInstance) -> GameState:
    """Replace a card across any zone of either player."""
    for pid in (PlayerID.P1, PlayerID.P2):
        player = state.get_player(pid)
        if player.leader.instance_id == instance_id:
            new_player = dataclasses.replace(player, leader=new_card)
            return _replace_player(state, pid, new_player)
        for zone_name in ("hand", "deck", "field", "life", "trash"):
            zone = getattr(player, zone_name)
            for i, c in enumerate(zone):
                if c.instance_id == instance_id:
                    new_zone = zone[:i] + (new_card,) + zone[i+1:]
                    new_player = dataclasses.replace(player, **{zone_name: new_zone})
                    return _replace_player(state, pid, new_player)
    raise ValueError(f"Card {instance_id} not found in any zone")
