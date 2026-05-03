"""Typed lookups over state.scoped_effects.

Each helper applies the same filter chain:
  1. Match target_instance_id
  2. Check applies_when against current state
  3. Filter by modification type
"""
from __future__ import annotations
from typing import Optional
from engine.game_state import GameState, PlayerID


def _is_active(se, state: GameState) -> bool:
    """Is this scoped effect currently active per its `applies_when` clause?"""
    if se.applies_when == "always":
        return True
    target_owner = _target_owner(state, se.target_instance_id)
    if target_owner is None:
        return True
    if se.applies_when == "your_turn":
        return state.active_player_id == target_owner
    if se.applies_when == "opponent_turn":
        return state.active_player_id != target_owner
    if se.applies_when == "during_battle":
        return state.battle_context is not None
    return True


def _target_owner(state: GameState, instance_id: str) -> Optional[PlayerID]:
    card = state.get_card(instance_id)
    return card.controller if card else None


def power_modifiers(state: GameState, instance_id: str) -> int:
    total = 0
    for se in state.scoped_effects:
        if se.target_instance_id != instance_id:
            continue
        if se.modification.get("type") != "PowerMod":
            continue
        if not _is_active(se, state):
            continue
        total += se.modification.get("amount", 0)
    return total


def is_refresh_blocked(state: GameState, instance_id: str) -> bool:
    """v2: returns True if any active PreventRefresh ScopedEffect targets this card."""
    for se in state.scoped_effects:
        if se.target_instance_id != instance_id:
            continue
        if se.modification.get("type") != "PreventRefresh":
            continue
        if _is_active(se, state):
            return True
    return False


def can_attack(state: GameState, instance_id: str) -> bool:
    """v2: returns False if any active CantAttack ScopedEffect targets this card."""
    for se in state.scoped_effects:
        if se.target_instance_id != instance_id:
            continue
        if se.modification.get("type") != "CantAttack":
            continue
        if _is_active(se, state):
            return False
    return True


def cost_reduction_for(state: GameState, controller: PlayerID, card_def) -> int:
    """v2: sum of CostReduction modifications applying to a card play.
    For v2 simplicity, only modifications without target_filter are considered;
    target_filter support deferred."""
    total = 0
    for se in state.scoped_effects:
        if se.modification.get("type") != "CostReduction":
            continue
        if not _is_active(se, state):
            continue
        if "target_filter" in se.modification:
            continue
        total += se.modification.get("amount", 0)
    return total


def granted_keywords(state: GameState, instance_id: str) -> frozenset[str]:
    found = set()
    for se in state.scoped_effects:
        if se.target_instance_id != instance_id:
            continue
        if se.modification.get("type") != "KeywordGrant":
            continue
        if not _is_active(se, state):
            continue
        kw = se.modification.get("keyword")
        if kw:
            found.add(kw)
    return frozenset(found)
