"""
engine/legal_actions.py
=======================
legal_actions(state, db) -> tuple[Action, ...]

The bot's view of "what can I do right now?" Enumerates every legal action
for the current phase. Bugs here cause silent failure - too few actions
restricts the bot, too many crashes the engine on dispatch.
"""
from __future__ import annotations
from typing import Optional
from engine.game_state import (
    GameState, Phase, PlayerID, PlayerState, Zone, CardInstance,
)
from engine.actions import (
    Action,
    ChooseFirst, AdvancePhase, RespondInput,
    PlayCard, ActivateAbility, AttachDon, EndTurn, DeclareAttack,
    DeclareBlocker, PassBlocker,
    PlayCounter, PassCounter,
    ActivateTrigger, PassTrigger,
)
from engine.card_db import CardDB
from engine.keywords import effective_keywords


def legal_actions(state: GameState, db: Optional[CardDB]) -> tuple[Action, ...]:
    """Return every legal action in the current state."""
    if state.phase == Phase.GAME_OVER:
        return ()

    if state.is_waiting_for_input():
        return _legal_respond_inputs(state)

    phase = state.phase

    if phase == Phase.SETUP:
        return (ChooseFirst("P1"), ChooseFirst("P2"))

    if phase in (Phase.REFRESH, Phase.DRAW, Phase.DON, Phase.END,
                 Phase.BATTLE_DECLARED, Phase.BATTLE_WHEN_ATK,
                 Phase.BATTLE_DAMAGE, Phase.BATTLE_CLEANUP):
        return (AdvancePhase(),)

    if phase == Phase.MAIN:
        return _legal_main_actions(state, db)

    if phase == Phase.BATTLE_BLOCKER:
        return _legal_blocker_actions(state, db)

    if phase == Phase.BATTLE_COUNTER:
        return _legal_counter_actions(state, db)

    if phase == Phase.BATTLE_TRIGGER:
        # Vanilla: never reached because BATTLE_DAMAGE skips to BATTLE_CLEANUP.
        # Defensive: offer Pass only.
        return (PassTrigger(),)

    return ()


def _legal_respond_inputs(state: GameState) -> tuple[RespondInput, ...]:
    """Generate RespondInput options matching pending_input.valid_choices.
    If min_choices is 0, also emit a 'skip' option (empty choices)."""
    pending = state.pending_input
    assert pending is not None
    options: list[RespondInput] = [RespondInput(choices=(c,)) for c in pending.valid_choices]
    if pending.min_choices == 0:
        options.append(RespondInput(choices=()))
    if not options:
        # min_choices > 0 but no valid choices — emit skip anyway as a fallback.
        options.append(RespondInput(choices=()))
    return tuple(options)


def _legal_main_actions(state: GameState, db: Optional[CardDB]) -> tuple[Action, ...]:
    """MAIN phase: PlayCard, AttachDon, DeclareAttack, EndTurn."""
    assert db is not None
    actions: list[Action] = [EndTurn()]
    active = state.active_player()

    # PlayCard for each affordable hand card
    for c in active.hand:
        cdef = db.get(c.definition_id)
        if cdef.cost is None:
            continue
        if active.don_field.active >= cdef.cost:
            actions.append(PlayCard(card_instance_id=c.instance_id))

    # AttachDon: one option per legal target if any active DON
    if active.don_field.active >= 1:
        actions.append(AttachDon(target_instance_id=active.leader.instance_id))
        for ch in active.field:
            actions.append(AttachDon(target_instance_id=ch.instance_id))

    # DeclareAttack: only if turn > 1 (rule 6-5-6-1)
    if state.turn_number > 1:
        from engine.dsl.lookups import can_attack
        attackers = [active.leader] + list(active.field)
        for atk in attackers:
            if atk.rested:
                continue
            if not can_attack(state, atk.instance_id):
                continue
            for tgt in _attack_targets(state, atk):
                actions.append(DeclareAttack(
                    attacker_instance_id=atk.instance_id,
                    target_instance_id=tgt.instance_id,
                ))

    # ActivateAbility for ActivateMain triggers on field cards (T5/v2).
    # Pre-check cost feasibility to avoid the bot enumerating illegal options.
    candidates = [active.leader] + list(active.field)
    for card in candidates:
        cdef = db.get(card.definition_id)
        for i, trigger in enumerate(cdef.triggers or ()):
            if trigger.get("on") != "ActivateMain":
                continue
            if trigger.get("once_per_turn") and card.instance_id in active.once_per_turn_used:
                continue
            if not _can_pay_cost(state, card, trigger.get("cost", [])):
                continue
            actions.append(ActivateAbility(
                card_instance_id=card.instance_id, trigger_index=i,
            ))

    return tuple(actions)


def _can_pay_cost(state: GameState, card: CardInstance, cost_array: list) -> bool:
    """Pre-flight check: would the cost array be payable from the current state?"""
    active = state.active_player()
    don_needed = 0
    rest_self_needed = False
    for c in cost_array:
        t = c.get("type")
        if t == "RestDon":
            don_needed += c.get("amount", 1)
        elif t == "RestSelf":
            rest_self_needed = True
    if don_needed > active.don_field.active:
        return False
    if rest_self_needed and card.rested:
        return False
    return True


def _attack_targets(state: GameState, attacker: CardInstance) -> list[CardInstance]:
    """Valid targets: opponent's leader + opponent's rested chars."""
    opp = state.inactive_player()
    targets: list[CardInstance] = [opp.leader]
    for ch in opp.field:
        if ch.rested:
            targets.append(ch)
    return targets


def _legal_blocker_actions(state: GameState, db: Optional[CardDB]) -> tuple[Action, ...]:
    """BATTLE_BLOCKER: DeclareBlocker for each active defender Character with Blocker; PassBlocker."""
    assert db is not None
    assert state.battle_context is not None
    actions: list[Action] = [PassBlocker()]
    attacker = state.get_card(state.battle_context.attacker_id)
    if attacker is not None:
        if "Unblockable" in effective_keywords(attacker, db, state):
            return (PassBlocker(),)
    defender = state.inactive_player()
    for ch in defender.field:
        if ch.rested:
            continue
        kws = effective_keywords(ch, db, state)
        if "Blocker" in kws:
            actions.append(DeclareBlocker(blocker_instance_id=ch.instance_id))
    return tuple(actions)


def _legal_counter_actions(state: GameState, db: Optional[CardDB]) -> tuple[Action, ...]:
    """BATTLE_COUNTER: PlayCounter for each hand card with counter > 0; PassCounter."""
    assert db is not None
    actions: list[Action] = [PassCounter()]
    defender = state.inactive_player()
    for c in defender.hand:
        cdef = db.get(c.definition_id)
        if cdef.counter is not None and cdef.counter > 0:
            actions.append(PlayCounter(card_instance_id=c.instance_id))
    return tuple(actions)
