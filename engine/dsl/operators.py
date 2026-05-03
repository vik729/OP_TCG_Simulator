"""Operator (effect-verb) dispatchers.

Each operator is a function:
    apply_X(node, state, *, source_controller, db, source_id, inputs, choice_index)
        -> (new_state, optional_input_request, new_choice_index)

`apply()` is the dispatch entry. Combinator nodes are routed to
engine.dsl.combinators.apply.
"""
from __future__ import annotations
import dataclasses
from typing import Optional
from engine.game_state import (
    GameState, PlayerID, Zone, DonField, InputRequest, ScopedEffect,
)
from engine.card_db import CardDB
from engine.dsl.filters import find_targets


_UNTIL_TO_EXPIRES_AT = {
    "end_of_battle":         "BATTLE_CLEANUP",
    "end_of_this_turn":      "END_TURN",
    "end_of_opponent_turn":  "END_TURN",
    "end_of_your_next_turn": "END_TURN",
}


def apply(node: dict, state: GameState, *,
          source_controller: PlayerID, db: CardDB, source_id: Optional[str],
          inputs: tuple, choice_index: int):
    """Dispatch a DSL node by its `type` field."""
    t = node.get("type")
    fn = _OPERATORS.get(t)
    if fn is None:
        from engine.dsl.combinators import apply as combinator_apply
        return combinator_apply(node, state, source_controller=source_controller,
                                db=db, source_id=source_id, inputs=inputs,
                                choice_index=choice_index)
    return fn(node, state, source_controller=source_controller, db=db,
              source_id=source_id, inputs=inputs, choice_index=choice_index)


def _replace_player(state: GameState, pid: PlayerID, new_player) -> GameState:
    if pid == PlayerID.P1:
        return dataclasses.replace(state, p1=new_player)
    return dataclasses.replace(state, p2=new_player)


def _replace_card(state: GameState, instance_id: str, new_card) -> GameState:
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
    return state


def _request_target_choice(node, state, *, source_controller, db, source_id,
                           choice_index, prompt_prefix: str):
    target_filter = node.get("target", {})
    candidates = find_targets(target_filter, state,
                              source_controller=source_controller, db=db,
                              source_id=source_id)
    valid_ids = tuple(c.instance_id for c in candidates)
    max_n = node.get("max_choices", 1)
    min_n = node.get("min_choices", 0)

    # Auto-skip: if no valid targets and selection is optional, consume the
    # choice slot as an empty selection rather than stalling on a question
    # the player can't answer.
    if not valid_ids and min_n == 0:
        return state, None, choice_index + 1

    request = InputRequest(
        request_type="ChooseTargets",
        prompt=f"{prompt_prefix}: choose up to {max_n}",
        valid_choices=valid_ids,
        min_choices=min_n,
        max_choices=max_n,
        resume_context={"choice_index": choice_index},
    )
    new_state = dataclasses.replace(state, pending_input=request)
    return new_state, request, choice_index


def _resolve_expires_at(node, state):
    until = node.get("until", "end_of_battle")
    expires_at = _UNTIL_TO_EXPIRES_AT.get(until)
    if expires_at is None:
        raise ValueError(f"Unknown `until` value: {until!r}")
    if until == "end_of_this_turn":
        return expires_at, None
    if until == "end_of_opponent_turn":
        return expires_at, state.turn_number + 1
    if until == "end_of_your_next_turn":
        return expires_at, state.turn_number + 2
    return expires_at, None


# ── Operators ─────────────────────────────────────────────────────────────────

def _apply_draw(node, state, *, source_controller, db, source_id, inputs, choice_index):
    count = node.get("count", 1)
    player = state.get_player(source_controller)
    actual = min(count, len(player.deck))
    drawn = list(player.deck[:actual])
    new_deck = player.deck[actual:]
    new_hand = player.hand + tuple(
        dataclasses.replace(c, zone=Zone.HAND) for c in drawn
    )
    new_player = dataclasses.replace(player, deck=new_deck, hand=new_hand)
    return _replace_player(state, source_controller, new_player), None, choice_index


def _apply_ko(node, state, *, source_controller, db, source_id, inputs, choice_index):
    if choice_index >= len(inputs):
        return _request_target_choice(node, state, source_controller=source_controller,
                                      db=db, source_id=source_id, choice_index=choice_index,
                                      prompt_prefix="KO target")
    chosen_ids = inputs[choice_index]
    new_state = state
    for cid in chosen_ids:
        new_state = _ko_card(new_state, cid)
    return new_state, None, choice_index + 1


def _ko_card(state: GameState, instance_id: str) -> GameState:
    card = state.get_card(instance_id)
    if card is None:
        return state
    owner_state = state.get_player(card.controller)
    new_field = tuple(c for c in owner_state.field if c.instance_id != instance_id)
    don_returned = card.attached_don
    new_don = DonField(
        active=owner_state.don_field.active,
        rested=owner_state.don_field.rested + don_returned,
    )
    new_trash = owner_state.trash + (
        dataclasses.replace(card, zone=Zone.TRASH, rested=False, attached_don=0),
    )
    new_owner = dataclasses.replace(owner_state, field=new_field, trash=new_trash, don_field=new_don)
    return _replace_player(state, card.controller, new_owner)


def _apply_bounce(node, state, *, source_controller, db, source_id, inputs, choice_index):
    if choice_index >= len(inputs):
        return _request_target_choice(node, state, source_controller=source_controller,
                                      db=db, source_id=source_id, choice_index=choice_index,
                                      prompt_prefix="Bounce target")
    chosen_ids = inputs[choice_index]
    new_state = state
    for cid in chosen_ids:
        new_state = _bounce_card(new_state, cid)
    return new_state, None, choice_index + 1


def _bounce_card(state: GameState, instance_id: str) -> GameState:
    card = state.get_card(instance_id)
    if card is None:
        return state
    owner_state = state.get_player(card.controller)
    new_field = tuple(c for c in owner_state.field if c.instance_id != instance_id)
    don_returned = card.attached_don
    new_don = DonField(
        active=owner_state.don_field.active,
        rested=owner_state.don_field.rested + don_returned,
    )
    new_hand = owner_state.hand + (
        dataclasses.replace(card, zone=Zone.HAND, rested=False, attached_don=0),
    )
    new_owner = dataclasses.replace(owner_state, field=new_field, hand=new_hand, don_field=new_don)
    return _replace_player(state, card.controller, new_owner)


def _apply_add_don(node, state, *, source_controller, db, source_id, inputs, choice_index):
    count = node.get("count", 1)
    state_kind = node.get("state", "active")
    player = state.get_player(source_controller)
    avail = min(count, player.don_deck_count)
    new_don = DonField(
        active=player.don_field.active + (avail if state_kind == "active" else 0),
        rested=player.don_field.rested + (avail if state_kind == "rested" else 0),
    )
    new_player = dataclasses.replace(player,
                                     don_deck_count=player.don_deck_count - avail,
                                     don_field=new_don)
    return _replace_player(state, source_controller, new_player), None, choice_index


def _apply_attach_don(node, state, *, source_controller, db, source_id, inputs, choice_index):
    if choice_index >= len(inputs):
        return _request_target_choice(node, state, source_controller=source_controller,
                                      db=db, source_id=source_id, choice_index=choice_index,
                                      prompt_prefix="Give DON to target")
    chosen_ids = inputs[choice_index]
    count = node.get("count", 1)
    state_kind = node.get("state", "active")
    new_state = state
    for cid in chosen_ids:
        new_state = _attach_don_to(new_state, source_controller, cid, count, state_kind)
    return new_state, None, choice_index + 1


def _attach_don_to(state, controller, target_id, count, state_kind):
    player = state.get_player(controller)
    avail = (player.don_field.active if state_kind == "active"
             else player.don_field.rested)
    n = min(count, avail)
    if n == 0:
        return state
    target = state.get_card(target_id)
    if target is None:
        return state
    new_target = dataclasses.replace(target, attached_don=target.attached_don + n)
    new_don = DonField(
        active=player.don_field.active - (n if state_kind == "active" else 0),
        rested=player.don_field.rested - (n if state_kind == "rested" else 0),
    )
    new_player = dataclasses.replace(player, don_field=new_don)
    state2 = _replace_player(state, controller, new_player)
    return _replace_card(state2, target_id, new_target)


def _apply_trash_hand(node, state, *, source_controller, db, source_id, inputs, choice_index):
    chooser = node.get("chooser", "controller")
    chooser_id = source_controller if chooser == "controller" else source_controller.opponent()
    target_player = state.get_player(chooser_id)

    if choice_index >= len(inputs):
        candidate_ids = tuple(c.instance_id for c in target_player.hand)
        count = node.get("count", 1)
        request = InputRequest(
            request_type="ChooseCards",
            prompt=f"Trash {count} from {chooser_id.value} hand",
            valid_choices=candidate_ids,
            min_choices=count,
            max_choices=count,
            resume_context={"choice_index": choice_index},
        )
        new_state = dataclasses.replace(state, pending_input=request)
        return new_state, request, choice_index

    chosen_ids = inputs[choice_index]
    new_hand = tuple(c for c in target_player.hand if c.instance_id not in chosen_ids)
    moved = tuple(
        dataclasses.replace(c, zone=Zone.TRASH)
        for c in target_player.hand if c.instance_id in chosen_ids
    )
    new_trash = target_player.trash + moved
    new_player = dataclasses.replace(target_player, hand=new_hand, trash=new_trash)
    return _replace_player(state, chooser_id, new_player), None, choice_index + 1


def _apply_give_power(node, state, *, source_controller, db, source_id, inputs, choice_index):
    if choice_index >= len(inputs):
        return _request_target_choice(node, state, source_controller=source_controller,
                                      db=db, source_id=source_id, choice_index=choice_index,
                                      prompt_prefix="Give power to target")
    chosen_ids = inputs[choice_index]
    amount = node.get("amount", 0)
    expires_at, expires_at_turn = _resolve_expires_at(node, state)
    applies_when = node.get("applies_when", "always")
    new_effects = list(state.scoped_effects)
    for cid in chosen_ids:
        new_effects.append(ScopedEffect(
            target_instance_id=cid,
            modification={"type": "PowerMod", "amount": amount},
            applies_when=applies_when,
            expires_at=expires_at,
            expires_at_turn=expires_at_turn,
        ))
    new_state = dataclasses.replace(state, scoped_effects=tuple(new_effects))
    return new_state, None, choice_index + 1


def _apply_grant_keyword(node, state, *, source_controller, db, source_id, inputs, choice_index):
    if choice_index >= len(inputs):
        return _request_target_choice(node, state, source_controller=source_controller,
                                      db=db, source_id=source_id, choice_index=choice_index,
                                      prompt_prefix="Grant keyword to target")
    chosen_ids = inputs[choice_index]
    keyword = node.get("keyword")
    expires_at, expires_at_turn = _resolve_expires_at(node, state)
    applies_when = node.get("applies_when", "always")
    new_effects = list(state.scoped_effects)
    for cid in chosen_ids:
        new_effects.append(ScopedEffect(
            target_instance_id=cid,
            modification={"type": "KeywordGrant", "keyword": keyword},
            applies_when=applies_when,
            expires_at=expires_at,
            expires_at_turn=expires_at_turn,
        ))
    new_state = dataclasses.replace(state, scoped_effects=tuple(new_effects))
    return new_state, None, choice_index + 1


_OPERATORS = {
    "Draw":         _apply_draw,
    "KO":           _apply_ko,
    "Bounce":       _apply_bounce,
    "AddDon":       _apply_add_don,
    "AttachDon":    _apply_attach_don,
    "TrashHand":    _apply_trash_hand,
    "GivePower":    _apply_give_power,
    "GrantKeyword": _apply_grant_keyword,
}
