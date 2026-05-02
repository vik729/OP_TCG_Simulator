"""
engine/rng.py
=============
Splittable seed RNG helper.

The engine treats randomness as a single integer seed stored on GameState.rng_state.
Each time the engine needs randomness, it calls split_rng(state.rng_state) to get:
  1. A random.Random instance for this consumption
  2. A new integer state to store back on GameState

This pattern guarantees:
  - Deterministic replay: same starting seed + same action sequence -> same trace
  - No global RNG state - every consumption is local to the step that needs it
  - Forks are free: clone state, branch with different actions, RNG state branches too

The bot has its OWN RNG, separate from state.rng_state. Bot RNG is owned by the
caller (e.g. play.py) and is not part of GameState.
"""
from __future__ import annotations
import random


def split_rng(rng_state: int) -> tuple[random.Random, int]:
    """
    Get a random.Random instance for one consumption + the new state to store.

    Usage:
        rng, new_state = split_rng(state.rng_state)
        shuffled = tuple(rng.sample(deck, len(deck)))
        new_game_state = dataclasses.replace(state, rng_state=new_state, ...)
    """
    rng = random.Random(rng_state)
    next_state = rng.randint(0, 2**63 - 1)
    return rng, next_state
