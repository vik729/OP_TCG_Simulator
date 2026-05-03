"""Condition evaluator for `If` nodes. Returns bool."""
from __future__ import annotations
from typing import Optional
from engine.game_state import GameState, PlayerID
from engine.card_db import CardDB
from engine.dsl.filters import find_targets


_OPS = {
    "ge": lambda a, b: a >= b,
    "gt": lambda a, b: a > b,
    "le": lambda a, b: a <= b,
    "lt": lambda a, b: a < b,
    "eq": lambda a, b: a == b,
    "ne": lambda a, b: a != b,
}


def evaluate(cond: dict, state: GameState, *,
             source_controller: PlayerID, db: CardDB,
             source_id: Optional[str] = None) -> bool:
    t = cond.get("type")
    op_fn = _OPS.get(cond.get("op", "ge"))
    if op_fn is None:
        raise ValueError(f"Unknown op {cond.get('op')!r} in condition {cond}")
    value = cond.get("value", 0)

    if t == "DonCount":
        player = state.get_player(source_controller)
        actual = player.don_field.active + player.don_field.rested
        return op_fn(actual, value)

    if t == "LifeCount":
        return op_fn(len(state.get_player(source_controller).life), value)

    if t == "HandCount":
        return op_fn(len(state.get_player(source_controller).hand), value)

    if t == "ControllerHas":
        f = cond.get("filter", {})
        targets = find_targets(f, state, source_controller=source_controller,
                               db=db, source_id=source_id)
        return op_fn(len(targets), value)

    if t == "SourceAttachedDon":
        if source_id is None:
            raise ValueError("SourceAttachedDon needs source_id")
        card = state.get_card(source_id)
        if card is None:
            return False
        return op_fn(card.attached_don, value)

    raise ValueError(f"Unknown condition type {t!r}")
