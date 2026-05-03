"""Combinators: Sequence, If, Choice, ForEach.

Same signature as operators: (node, state, ...) ->
(state, optional_input_request, choice_index).
"""
from __future__ import annotations
import dataclasses
from typing import Optional
from engine.game_state import GameState, PlayerID, InputRequest
from engine.card_db import CardDB
from engine.dsl.conditions import evaluate as evaluate_condition


def apply(node: dict, state: GameState, *,
          source_controller: PlayerID, db: CardDB, source_id: Optional[str],
          inputs: tuple, choice_index: int):
    t = node.get("type")
    if t == "Sequence":
        return _apply_sequence(node, state, source_controller=source_controller,
                               db=db, source_id=source_id, inputs=inputs,
                               choice_index=choice_index)
    if t == "If":
        return _apply_if(node, state, source_controller=source_controller,
                         db=db, source_id=source_id, inputs=inputs,
                         choice_index=choice_index)
    if t == "Choice":
        return _apply_choice(node, state, source_controller=source_controller,
                             db=db, source_id=source_id, inputs=inputs,
                             choice_index=choice_index)
    if t == "ForEach":
        return _apply_for_each(node, state, source_controller=source_controller,
                               db=db, source_id=source_id, inputs=inputs,
                               choice_index=choice_index)
    raise ValueError(f"Unknown DSL node type: {t!r}")


def _apply_sequence(node, state, *, source_controller, db, source_id, inputs, choice_index):
    from engine.dsl.operators import apply as op_apply
    new_state = state
    idx = choice_index
    for step in node.get("steps", []):
        new_state, req, idx = op_apply(step, new_state,
                                       source_controller=source_controller,
                                       db=db, source_id=source_id,
                                       inputs=inputs, choice_index=idx)
        if req is not None:
            return new_state, req, idx
    return new_state, None, idx


def _apply_if(node, state, *, source_controller, db, source_id, inputs, choice_index):
    from engine.dsl.operators import apply as op_apply
    cond = node.get("condition", {})
    if evaluate_condition(cond, state, source_controller=source_controller,
                          db=db, source_id=source_id):
        return op_apply(node["then"], state,
                        source_controller=source_controller, db=db,
                        source_id=source_id, inputs=inputs, choice_index=choice_index)
    if "else" in node:
        return op_apply(node["else"], state,
                        source_controller=source_controller, db=db,
                        source_id=source_id, inputs=inputs, choice_index=choice_index)
    return state, None, choice_index


def _apply_choice(node, state, *, source_controller, db, source_id, inputs, choice_index):
    from engine.dsl.operators import apply as op_apply
    if choice_index >= len(inputs):
        request = InputRequest(
            request_type="YesNo",
            prompt=node.get("prompt", "May activate effect?"),
            valid_choices=("yes", "no"),
            min_choices=1,
            max_choices=1,
            resume_context={"choice_index": choice_index},
        )
        return dataclasses.replace(state, pending_input=request), request, choice_index
    answer = inputs[choice_index]
    if answer == ("yes",):
        return op_apply(node["effect"], state,
                        source_controller=source_controller, db=db,
                        source_id=source_id, inputs=inputs, choice_index=choice_index + 1)
    return state, None, choice_index + 1


def _apply_for_each(node, state, *, source_controller, db, source_id, inputs, choice_index):
    from engine.dsl.operators import apply as op_apply
    from engine.dsl.filters import find_targets
    targets = find_targets(node.get("filter", {}), state,
                           source_controller=source_controller, db=db, source_id=source_id)
    new_state = state
    idx = choice_index
    for t in targets:
        inner = dict(node.get("do", {}))
        new_state, req, idx = op_apply(inner, new_state,
                                       source_controller=source_controller, db=db,
                                       source_id=t.instance_id, inputs=inputs,
                                       choice_index=idx)
        if req is not None:
            return new_state, req, idx
    return new_state, None, idx
