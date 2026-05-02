"""
engine/phase_machine.py
=======================
Defines which Actions are legal in each Phase.

This is NOT a class or dataclass.  It is:
  1. LEGAL_ACTIONS  — dict[Phase, frozenset[type]] saying what's valid when
  2. Helper functions for the engine
  3. PHASE_ORDER    — tuple used to garbage-collect TempEffects by phase position

Actual phase transitions live in engine/step.py because they depend on full
GameState context, not just the current phase.
"""
from __future__ import annotations
from engine.game_state import Phase
from engine.actions import (
    Action,
    ChooseFirst,
    PlayCard, ActivateAbility, AttachDon, DeclareAttack, EndTurn,
    DeclareBlocker, PassBlocker,
    PlayCounter, PassCounter,
    ActivateTrigger, PassTrigger,
    RespondInput,
)


# ── Legal action map ───────────────────────────────────────────────────────────

LEGAL_ACTIONS: dict[Phase, frozenset[type]] = {
    Phase.SETUP: frozenset({ChooseFirst}),

    # Automatic phases — engine advances without player input
    Phase.REFRESH: frozenset(),
    Phase.DRAW:    frozenset(),
    Phase.DON:     frozenset(),

    Phase.MAIN: frozenset({
        PlayCard,
        ActivateAbility,
        AttachDon,
        DeclareAttack,
        EndTurn,
    }),

    Phase.END: frozenset(),

    # Battle sub-phases
    Phase.BATTLE_DECLARED: frozenset(),
    Phase.BATTLE_WHEN_ATK: frozenset(),
    Phase.BATTLE_BLOCKER:  frozenset({DeclareBlocker, PassBlocker}),
    Phase.BATTLE_COUNTER:  frozenset({PlayCounter, PassCounter}),
    Phase.BATTLE_DAMAGE:   frozenset(),
    Phase.BATTLE_TRIGGER:  frozenset({ActivateTrigger, PassTrigger}),
    Phase.BATTLE_CLEANUP:  frozenset(),

    Phase.GAME_OVER: frozenset(),
}


# ── Core helpers ───────────────────────────────────────────────────────────────

def is_automatic(phase: Phase) -> bool:
    """True if this phase has no player decisions — engine advances automatically."""
    return len(LEGAL_ACTIONS[phase]) == 0


def legal_action_types(phase: Phase) -> frozenset[type]:
    """Return the Action types valid in this phase (ignoring pending_input)."""
    return LEGAL_ACTIONS[phase]


def is_legal_action(phase: Phase, action: Action, has_pending_input: bool) -> bool:
    """
    The single source of truth for action legality.

    Rule 0: GAME_OVER is terminal — nothing is ever legal.
    Rule 1: if pending_input is set, the ONLY valid action is RespondInput.
    Rule 2: otherwise, check the LEGAL_ACTIONS map for the current phase.
    """
    if phase == Phase.GAME_OVER:
        return False  # terminal — nothing is ever legal
    if has_pending_input:
        return isinstance(action, RespondInput)
    return type(action) in LEGAL_ACTIONS[phase]


# ── Phase ordering (for TempEffect expiry) ────────────────────────────────────

PHASE_ORDER: tuple[Phase, ...] = (
    Phase.REFRESH,
    Phase.DRAW,
    Phase.DON,
    Phase.MAIN,
    Phase.BATTLE_DECLARED,
    Phase.BATTLE_WHEN_ATK,
    Phase.BATTLE_BLOCKER,
    Phase.BATTLE_COUNTER,
    Phase.BATTLE_DAMAGE,
    Phase.BATTLE_TRIGGER,
    Phase.BATTLE_CLEANUP,
    Phase.END,
)

_PHASE_INDEX: dict[Phase, int] = {p: i for i, p in enumerate(PHASE_ORDER)}


def phase_has_passed(current: Phase, expires_after: Phase) -> bool:
    """
    True if current is strictly after expires_after in turn order.
    Returns False safely if either phase is not in PHASE_ORDER.
    """
    ci = _PHASE_INDEX.get(current)
    ei = _PHASE_INDEX.get(expires_after)
    if ci is None or ei is None:
        return False
    return ci > ei


def defending_player_phases() -> frozenset[Phase]:
    """Phases where the defending (inactive) player submits actions."""
    return frozenset({
        Phase.BATTLE_BLOCKER,
        Phase.BATTLE_COUNTER,
        Phase.BATTLE_TRIGGER,
    })
