"""
engine/actions.py
=================
All legal player actions, as frozen dataclasses.

Actions are the only way to advance GameState.  They are:
  - Typed     — the engine pattern-matches on the concrete type
  - Immutable — frozen dataclasses, safe to store and replay
  - Serialisable — every field is a plain Python primitive (str, int, tuple)

Nothing in here mutates state.  step(state, action) reads an Action
and returns a new GameState.
"""
from __future__ import annotations
from dataclasses import dataclass


class Action:
    """Marker base class.  Use isinstance(action, Action) for type guards."""
    pass


# ── Pre-game ───────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ChooseFirst(Action):
    """Decide which player takes the first turn (coin flip result)."""
    first_player_id: str   # "P1" or "P2"


@dataclass(frozen=True)
class AdvancePhase(Action):
    """
    Advance the game past an automatic phase. Required for every automatic phase
    (REFRESH, DRAW, DON, END, BATTLE_DECLARED, BATTLE_WHEN_ATK, BATTLE_DAMAGE,
    BATTLE_CLEANUP). The handler for this action performs the phase's logic
    (e.g. drawing the card during DRAW, unrooting during REFRESH) and transitions
    to the next phase.

    BATTLE_TRIGGER is NOT an automatic phase — it requires ActivateTrigger or
    PassTrigger, not AdvancePhase.
    """
    pass


# ── Main phase ─────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class PlayCard(Action):
    """
    Play a card from hand onto the field.
    The engine will rest (card.cost + extra_don) active Don cards.
    extra_don lets you pay more than the base cost to attach Don to the card.
    """
    card_instance_id: str
    extra_don:        int = 0   # additional Don rested beyond base card cost


@dataclass(frozen=True)
class ActivateAbility(Action):
    """
    Activate an [Activate: Main] or [Main] triggered ability on a card.
    trigger_index selects which trigger to fire (most cards have just one).
    """
    card_instance_id: str
    trigger_index:    int = 0


@dataclass(frozen=True)
class AttachDon(Action):
    """
    Attach one active DON!! card from your field to a character or your leader.
    The Don card is rested as part of the attachment — it stays attached.
    """
    target_instance_id: str


@dataclass(frozen=True)
class EndTurn(Action):
    """Signal the end of your Main phase.  Transitions to the End phase."""
    pass


# ── Battle ─────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class DeclareAttack(Action):
    """
    Declare an attack from an un-rested character (or leader).
    Valid target: opponent's leader, or any character on opponent's field.
    Transitions from MAIN → BATTLE_DECLARED.
    """
    attacker_instance_id: str
    target_instance_id:   str


@dataclass(frozen=True)
class DeclareBlocker(Action):
    """
    Switch the current attack target to a character with [Blocker].
    Only the defending player may submit this, during BATTLE_BLOCKER phase.
    """
    blocker_instance_id: str


@dataclass(frozen=True)
class PassBlocker(Action):
    """Decline to use a Blocker.  Closes the blocker window."""
    pass


@dataclass(frozen=True)
class PlayCounter(Action):
    """
    Play a Counter card from hand during the counter window.
    The card's [Counter] effect resolves immediately; card goes to trash.
    Multiple counters may be played sequentially.
    """
    card_instance_id: str


@dataclass(frozen=True)
class PassCounter(Action):
    """Close the counter window.  No more counters may be played this battle."""
    pass


@dataclass(frozen=True)
class ActivateTrigger(Action):
    """
    Activate the [Trigger] effect on the life card just revealed.
    Only valid during BATTLE_TRIGGER phase when the revealed card has a trigger.
    """
    pass


@dataclass(frozen=True)
class PassTrigger(Action):
    """
    Decline the [Trigger] effect.
    The revealed life card moves to the defending player's hand.
    """
    pass


# ── Input response ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class RespondInput(Action):
    """
    Provide an answer to a pending InputRequest.

    When GameState.pending_input is not None, this is the ONLY valid action.
    `choices` must be a subset of pending_input.valid_choices, with length
    between pending_input.min_choices and pending_input.max_choices.

    Examples:
      RespondInput(choices=("p1-12",))         # chose one target by instance_id
      RespondInput(choices=("yes",))           # answered "you may" with yes
      RespondInput(choices=())                 # answered "up to 1" by choosing none
    """
    choices: tuple[str, ...]
