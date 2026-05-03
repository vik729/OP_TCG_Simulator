"""
engine/step.py
==============
The single entry point: step(GameState, Action, db) -> GameState.

Dispatches actions to per-type handlers. After the handler runs, calls
check_win_conditions to detect DECK_OUT. (LIFE_AND_LEADER_HIT is set
inline by combat.)

Vanilla MVP: ActivateAbility raises NotImplementedError; resolver is a
no-op stub.
"""
from __future__ import annotations
import dataclasses
from typing import Optional
from engine.game_state import (
    GameState, Phase, PlayerID, CardInstance, Zone, DonField, WinReason,
)
from engine.actions import (
    Action,
    ChooseFirst, AdvancePhase, RespondInput,
    PlayCard, ActivateAbility, AttachDon, EndTurn, DeclareAttack,
    DeclareBlocker, PassBlocker,
    PlayCounter, PassCounter,
    ActivateTrigger, PassTrigger,
)
from engine.phase_machine import is_legal_action
from engine.card_db import CardDB
from engine.win_check import check_win_conditions
from engine.resolver import resolve_top
from engine import setup as setup_module
from engine import combat as combat_module


class IllegalActionError(Exception):
    pass


def step(state: GameState, action: Action, db: CardDB) -> GameState:
    """Apply an action to the state, returning a new state."""
    if not is_legal_action(state.phase, action, state.is_waiting_for_input()):
        raise IllegalActionError(
            f"Action {type(action).__name__} not legal in phase {state.phase}"
            f" (pending_input={state.is_waiting_for_input()})"
        )

    handler = _dispatch(action)
    new_state = handler(state, action, db)
    new_state = check_win_conditions(new_state)
    new_state = resolve_top(new_state, db)
    return new_state


def _dispatch(action: Action):
    t = type(action)
    if t is ChooseFirst:
        return _handle_choose_first
    if t is AdvancePhase:
        return _handle_advance_phase
    if t is RespondInput:
        return _handle_respond_input
    if t is PlayCard:
        return _handle_play_card
    if t is ActivateAbility:
        return _handle_activate_ability
    if t is AttachDon:
        return _handle_attach_don
    if t is EndTurn:
        return _handle_end_turn
    if t is DeclareAttack:
        return combat_module.begin_attack
    if t is DeclareBlocker:
        return combat_module.handle_blocker
    if t is PassBlocker:
        return combat_module.handle_pass_blocker
    if t is PlayCounter:
        return combat_module.handle_counter
    if t is PassCounter:
        return combat_module.handle_pass_counter
    if t is ActivateTrigger:
        return combat_module.handle_trigger
    if t is PassTrigger:
        return combat_module.handle_pass_trigger
    raise ValueError(f"No handler for action type {t.__name__}")


def _handle_choose_first(state, action, db):
    return setup_module.handle_choose_first(state, action, db)


def _handle_respond_input(state, action, db):
    if state.phase == Phase.SETUP:
        return setup_module.handle_setup_respond_input(state, action, db)
    if not state.effect_stack:
        raise IllegalActionError("RespondInput received but effect_stack is empty")
    if state.pending_input is None:
        raise IllegalActionError("RespondInput received but no pending_input is set")
    top = state.effect_stack[-1]
    new_top = dataclasses.replace(
        top,
        inputs_collected=top.inputs_collected + (action.choices,),
    )
    new_stack = state.effect_stack[:-1] + (new_top,)
    return dataclasses.replace(
        state, effect_stack=new_stack, pending_input=None,
    )


def _handle_advance_phase(state, action, db):
    p = state.phase
    if p == Phase.REFRESH:
        return _do_refresh(state, db)
    if p == Phase.DRAW:
        return _do_draw(state, db)
    if p == Phase.DON:
        return _do_don(state, db)
    if p == Phase.END:
        return _do_end(state, db)
    if p in (Phase.BATTLE_DECLARED, Phase.BATTLE_WHEN_ATK,
             Phase.BATTLE_DAMAGE, Phase.BATTLE_CLEANUP):
        return combat_module.advance_battle(state, db)
    raise ValueError(f"AdvancePhase not valid in phase {p}")


def _do_refresh(state, db):
    """REFRESH: unrest all cards; return attached DON to cost area as active.
    Per rules 6-2-3 and 6-2-4. Then fire AtStartOfYourTurn triggers."""
    active = state.active_player()
    don_returned = active.leader.attached_don + sum(c.attached_don for c in active.field)
    from engine.dsl.lookups import is_refresh_blocked
    new_leader = dataclasses.replace(
        active.leader, attached_don=0,
        rested=is_refresh_blocked(state, active.leader.instance_id) and active.leader.rested,
    )
    new_field = tuple(
        dataclasses.replace(c, attached_don=0,
                             rested=is_refresh_blocked(state, c.instance_id) and c.rested)
        for c in active.field
    )
    new_don_field = DonField(
        active=active.don_field.active + active.don_field.rested + don_returned,
        rested=0,
    )
    new_active = dataclasses.replace(
        active,
        leader=new_leader,
        field=new_field,
        don_field=new_don_field,
        once_per_turn_used=frozenset(),
    )
    new_state = _replace_active_player(state, new_active)

    # Fire AtStartOfYourTurn triggers (after refresh, before draw)
    from engine.dsl.trigger_queue import find_triggers_for_event
    from engine.game_state import StackEntry
    from engine.dsl.resolver import resolve_top
    triggers = find_triggers_for_event(new_state, "AtStartOfYourTurn",
                                        new_state.active_player_id, db)
    for card, trigger in triggers:
        entry = StackEntry(
            effect=trigger["effect"],
            source_instance_id=card.instance_id,
            controller=card.controller,
            inputs_collected=(),
            initial_state_ref=new_state,
        )
        new_state = dataclasses.replace(
            new_state, effect_stack=new_state.effect_stack + (entry,)
        )
    new_state = resolve_top(new_state, db)
    if new_state.pending_input is not None:
        return new_state
    return dataclasses.replace(new_state, phase=Phase.DRAW)


def _do_draw(state, db):
    """DRAW: active player draws 1 card. P1 skips on turn 1 (rule 6-3-1)."""
    active = state.active_player()
    if state.turn_number == 1 and state.active_player_id == PlayerID.P1:
        return dataclasses.replace(state, phase=Phase.DON)
    if not active.deck:
        return dataclasses.replace(state, phase=Phase.DON)
    drawn = dataclasses.replace(active.deck[0], zone=Zone.HAND)
    new_active = dataclasses.replace(
        active,
        deck=active.deck[1:],
        hand=active.hand + (drawn,),
    )
    new_state = _replace_active_player(state, new_active)
    return dataclasses.replace(new_state, phase=Phase.DON)


def _do_don(state, db):
    """DON: place 2 DON cards face-up in cost area. P1 places 1 on turn 1 (rule 6-4-1)."""
    active = state.active_player()
    n = 2
    if state.turn_number == 1 and state.active_player_id == PlayerID.P1:
        n = 1
    avail = min(n, active.don_deck_count)
    new_active = dataclasses.replace(
        active,
        don_deck_count=active.don_deck_count - avail,
        don_field=DonField(
            active=active.don_field.active + avail,
            rested=active.don_field.rested,
        ),
    )
    new_state = _replace_active_player(state, new_active)
    return dataclasses.replace(new_state, phase=Phase.MAIN)


def _do_end(state, db):
    """END: fire EndOfYourTurn triggers; expire end-of-turn temp effects;
    flip turn player; advance turn."""
    # Fire EndOfYourTurn triggers (in current turn player's context)
    from engine.dsl.trigger_queue import find_triggers_for_event
    from engine.game_state import StackEntry
    from engine.dsl.resolver import resolve_top
    triggers = find_triggers_for_event(state, "EndOfYourTurn",
                                        state.active_player_id, db)
    for card, trigger in triggers:
        entry = StackEntry(
            effect=trigger["effect"],
            source_instance_id=card.instance_id,
            controller=card.controller,
            inputs_collected=(),
            initial_state_ref=state,
        )
        state = dataclasses.replace(
            state, effect_stack=state.effect_stack + (entry,)
        )
    state = resolve_top(state, db)
    if state.pending_input is not None:
        # Pause for player input; we'll resume here when RespondInput clears it.
        return state

    new_scoped = tuple(
        se for se in state.scoped_effects
        if not (se.expires_at == "END_TURN"
                and (se.expires_at_turn is None
                     or se.expires_at_turn == state.turn_number))
    )
    new_active_id = state.active_player_id.opponent()
    new_turn = state.turn_number + 1
    return dataclasses.replace(
        state,
        phase=Phase.REFRESH,
        active_player_id=new_active_id,
        turn_number=new_turn,
        scoped_effects=new_scoped,
    )


def _handle_play_card(state, action: PlayCard, db):
    """PlayCard: rest <cost> active DON, move card from hand to field, fire OnPlay triggers."""
    active = state.active_player()
    card = state.get_card(action.card_instance_id)
    if card is None:
        raise IllegalActionError(f"PlayCard: {action.card_instance_id} not found")
    cdef = db.get(card.definition_id)
    cost = cdef.cost or 0
    if active.don_field.active < cost:
        raise IllegalActionError(f"PlayCard: not enough DON ({active.don_field.active} < {cost})")
    new_don = DonField(
        active=active.don_field.active - cost,
        rested=active.don_field.rested + cost,
    )
    new_hand = tuple(c for c in active.hand if c.instance_id != card.instance_id)
    on_field = dataclasses.replace(card, zone=Zone.FIELD, rested=False)
    new_field = active.field + (on_field,)
    new_active = dataclasses.replace(
        active, hand=new_hand, field=new_field, don_field=new_don,
    )
    new_state = _replace_active_player(state, new_active)

    # Fire any OnPlay triggers on the played card.
    on_play_triggers = [t for t in (cdef.triggers or []) if t.get("on") == "OnPlay"]
    if on_play_triggers:
        from engine.game_state import StackEntry
        for trigger in on_play_triggers:
            entry = StackEntry(
                effect=trigger["effect"],
                source_instance_id=card.instance_id,
                controller=card.controller,
                inputs_collected=(),
                initial_state_ref=new_state,
            )
            new_state = dataclasses.replace(
                new_state, effect_stack=new_state.effect_stack + (entry,)
            )

    return new_state


def _handle_activate_ability(state, action: ActivateAbility, db):
    """v2: ActivateMain trigger handler.
    1. Resolve trigger by index from card's ActivateMain triggers.
    2. Enforce OPT.
    3. Pay all costs atomically (any failure -> abort).
    4. Mark OPT used.
    5. Push effect onto effect_stack."""
    card = state.get_card(action.card_instance_id)
    if card is None:
        raise IllegalActionError(f"ActivateAbility: card {action.card_instance_id} not found")
    cdef = db.get(card.definition_id)
    activate_triggers = [t for t in (cdef.triggers or ()) if t.get("on") == "ActivateMain"]
    if action.trigger_index >= len(activate_triggers):
        raise IllegalActionError(
            f"ActivateAbility: card has no ActivateMain trigger at index {action.trigger_index}")
    trigger = activate_triggers[action.trigger_index]

    active = state.active_player()
    if trigger.get("once_per_turn") and card.instance_id in active.once_per_turn_used:
        raise IllegalActionError(
            f"ActivateAbility: {card.instance_id} once per turn already used")

    # Pay costs atomically
    from engine.dsl.cost_helpers import apply_cost, ActivationCostFailed
    new_state = state
    for cost_node in trigger.get("cost", []):
        try:
            new_state = apply_cost(cost_node, new_state,
                                    source_controller=card.controller,
                                    source_id=card.instance_id)
        except ActivationCostFailed as e:
            raise IllegalActionError(f"ActivateAbility: cost failed - {e}")

    # Mark OPT used
    if trigger.get("once_per_turn"):
        new_active = dataclasses.replace(
            new_state.active_player(),
            once_per_turn_used=new_state.active_player().once_per_turn_used | {card.instance_id},
        )
        new_state = _replace_active_player(new_state, new_active)

    # Push effect onto stack
    from engine.game_state import StackEntry
    entry = StackEntry(
        effect=trigger["effect"],
        source_instance_id=card.instance_id,
        controller=card.controller,
        inputs_collected=(),
        initial_state_ref=new_state,
    )
    return dataclasses.replace(
        new_state, effect_stack=new_state.effect_stack + (entry,)
    )


def _handle_attach_don(state, action: AttachDon, db):
    active = state.active_player()
    if active.don_field.active < 1:
        raise IllegalActionError("AttachDon: no active DON")
    target = state.get_card(action.target_instance_id)
    if target is None:
        raise IllegalActionError(f"AttachDon: target {action.target_instance_id} not found")
    new_target = dataclasses.replace(target, attached_don=target.attached_don + 1)
    new_state = _replace_card_helper(state, action.target_instance_id, new_target)
    new_active = new_state.active_player()
    new_don = DonField(
        active=new_active.don_field.active - 1,
        rested=new_active.don_field.rested,
    )
    new_active = dataclasses.replace(new_active, don_field=new_don)
    return _replace_active_player(new_state, new_active)


def _handle_end_turn(state, action: EndTurn, db):
    return dataclasses.replace(state, phase=Phase.END)


def _replace_active_player(state, new_player):
    if state.active_player_id == PlayerID.P1:
        return dataclasses.replace(state, p1=new_player)
    return dataclasses.replace(state, p2=new_player)


def _replace_card_helper(state, instance_id: str, new_card):
    """Same as combat._replace_card - duplicated to avoid circular import."""
    for pid in (PlayerID.P1, PlayerID.P2):
        player = state.get_player(pid)
        if player.leader.instance_id == instance_id:
            new_player = dataclasses.replace(player, leader=new_card)
            return _set_player(state, pid, new_player)
        for zone_name in ("hand", "deck", "field", "life", "trash"):
            zone = getattr(player, zone_name)
            for i, c in enumerate(zone):
                if c.instance_id == instance_id:
                    new_zone = zone[:i] + (new_card,) + zone[i+1:]
                    new_player = dataclasses.replace(player, **{zone_name: new_zone})
                    return _set_player(state, pid, new_player)
    raise ValueError(f"Card {instance_id} not found")


def _set_player(state, pid, new_player):
    if pid == PlayerID.P1:
        return dataclasses.replace(state, p1=new_player)
    return dataclasses.replace(state, p2=new_player)
