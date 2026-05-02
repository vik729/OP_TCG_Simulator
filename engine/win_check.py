"""
engine/win_check.py
===================
Defeat condition checker.

Per rules section 1-2-1-1, the two defeat conditions are:
  1. LIFE_AND_LEADER_HIT (1-2-1-1-1): leader takes damage at 0 life.
  2. DECK_OUT (1-2-1-1-2): the player has 0 cards in their deck.

LIFE_AND_LEADER_HIT is detected at the moment damage is dealt - combat.py is
responsible for setting GAME_OVER + WinReason directly when the damage step
puts a player at 0 life with leader being hit. This module's job for that
condition is just to leave the state alone if it's already GAME_OVER.

DECK_OUT is detected here, because deck cards leave only via draw (in DRAW
phase) and select effects - both of which produce a state we then check.
"""
from __future__ import annotations
import dataclasses
from engine.game_state import GameState, Phase, PlayerID, WinReason


def check_win_conditions(state: GameState) -> GameState:
    """
    If a defeat condition is met, return a new state in GAME_OVER with winner
    and win_reason set. Otherwise return state unchanged.

    Already-GAME_OVER states pass through.
    """
    if state.phase == Phase.GAME_OVER:
        return state

    p1_deck_out = len(state.p1.deck) == 0
    p2_deck_out = len(state.p2.deck) == 0
    if p1_deck_out and p2_deck_out:
        # Tie-break: turn player wins (rule 1-3-10 spirit)
        loser = state.active_player_id.opponent()
        return dataclasses.replace(
            state,
            phase=Phase.GAME_OVER,
            winner=loser.opponent(),
            win_reason=WinReason.DECK_OUT,
        )
    if p1_deck_out:
        return dataclasses.replace(
            state,
            phase=Phase.GAME_OVER,
            winner=PlayerID.P2,
            win_reason=WinReason.DECK_OUT,
        )
    if p2_deck_out:
        return dataclasses.replace(
            state,
            phase=Phase.GAME_OVER,
            winner=PlayerID.P1,
            win_reason=WinReason.DECK_OUT,
        )

    return state
