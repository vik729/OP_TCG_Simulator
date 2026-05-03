"""Effect-stack resolver. Pops the top StackEntry, walks the DSL tree from the
entry's initial_state_ref using its inputs_collected at choice points.

If the walk completes -> entry is popped, returned state is the new state.
If the walk pauses (returns an InputRequest) -> entry stays on stack, the
state with pending_input set is returned.
"""
from __future__ import annotations
import dataclasses
from engine.game_state import GameState
from engine.card_db import CardDB
from engine.dsl.operators import apply as op_apply


def resolve_top(state: GameState, db: CardDB) -> GameState:
    if not state.effect_stack:
        return state
    if state.pending_input is not None:
        # Engine is waiting on a RespondInput. Don't try to resolve.
        return state

    entry = state.effect_stack[-1]
    initial = entry.initial_state_ref or state

    walked_state, request, _ = op_apply(
        entry.effect,
        initial,
        source_controller=entry.controller,
        db=db,
        source_id=entry.source_instance_id,
        inputs=entry.inputs_collected,
        choice_index=0,
    )

    if request is not None:
        # Pause — keep the entry on stack. Set pending_input on the current
        # state (preserve effect_stack and other state outside the entry).
        return dataclasses.replace(state, pending_input=request)

    # Complete: pop the entry. The walked_state already has all mutations
    # applied; just need to drop the popped entry from the effect_stack.
    new_stack = state.effect_stack[:-1]
    return dataclasses.replace(
        walked_state,
        effect_stack=new_stack,
        pending_input=None,
    )
