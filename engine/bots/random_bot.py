"""
engine/bots/random_bot.py
=========================
Uniform random policy over legal_actions.

The bot's RNG is independent of game RNG (state.rng_state). Caller (play.py
or test) owns the bot's random.Random instance.
"""
from __future__ import annotations
import random
from engine.game_state import GameState
from engine.actions import Action
from engine.legal_actions import legal_actions
from engine.card_db import CardDB


class NoLegalActionsError(Exception):
    pass


def random_legal_action(state: GameState, rng: random.Random,
                        db: CardDB) -> Action:
    """Pick a legal action uniformly at random."""
    actions = legal_actions(state, db)
    if not actions:
        raise NoLegalActionsError(f"No legal actions in {state.phase}")
    return rng.choice(actions)
