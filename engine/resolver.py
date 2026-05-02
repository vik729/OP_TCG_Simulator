"""
engine/resolver.py
==================
Effect stack resolver.

In the DSL phase (deferred - see docs/todos/DSL_PIPELINE.md), this module pops
StackEntries from GameState.effect_stack and interprets the embedded DSL dict
to mutate state.

In vanilla MVP, no card has any parsed triggers, so the effect_stack should
always be empty. This stub is invoked unconditionally by step() - empty stack
means no-op (state unchanged). A non-empty stack signals a bug (something
pushed onto the stack despite no DSL being implemented) and raises.
"""
from __future__ import annotations
from engine.game_state import GameState


def resolve_top(state: GameState) -> GameState:
    """
    Pop and resolve the top StackEntry. Empty stack = no-op.

    Vanilla MVP: empty stack is the ONLY valid case. A non-empty stack is a
    bug and raises NotImplementedError to surface it loudly.
    """
    if not state.effect_stack:
        return state
    raise NotImplementedError(
        "Resolver not implemented in vanilla MVP - see docs/todos/DSL_PIPELINE.md"
    )
