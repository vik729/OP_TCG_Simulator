"""
engine/game_state.py
====================
Immutable snapshot of the entire game at one moment in time.

Design rules:
- Every type here is a frozen dataclass or Enum.  Nothing mutates.
- step(state, action) in engine/step.py reads these and returns new copies.
- Given the same initial GameState + action sequence, output is always identical.
- GameState can be serialised to JSON and back without losing information.
"""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Optional


# ── Enums ─────────────────────────────────────────────────────────────────────

class Phase(Enum):
    """
    Every state the game can be in.
    The engine only accepts Actions that are listed as legal for the current Phase.
    Automatic phases (REFRESH, DRAW, DON) have no legal player actions —
    the engine advances them on its own.
    """
    # Pre-game
    SETUP = "setup"

    # Turn loop
    REFRESH = "refresh"          # unrest all cards — automatic
    DRAW    = "draw"             # draw 1 card — automatic
    DON     = "don"              # add DON!! cards — automatic
    MAIN    = "main"             # play cards, activate abilities, declare attacks
    END     = "end"              # end-of-turn triggers fire — automatic

    # Battle sub-phases (entered from MAIN, can repeat multiple times per turn)
    BATTLE_DECLARED  = "battle_declared"   # attack declared, before WhenAttacking
    BATTLE_WHEN_ATK  = "battle_when_atk"   # WhenAttacking triggers resolving — auto
    BATTLE_BLOCKER   = "battle_blocker"    # defender may play a Blocker
    BATTLE_COUNTER   = "battle_counter"    # defender may play Counter cards
    BATTLE_DAMAGE    = "battle_damage"     # power compared, damage applied — auto
    BATTLE_TRIGGER   = "battle_trigger"    # [Trigger] on revealed life card
    BATTLE_CLEANUP   = "battle_cleanup"    # rest attacker, clear temp effects — auto

    # Terminal
    GAME_OVER = "game_over"


class Zone(Enum):
    """Every zone a card can occupy. A card is always in exactly one zone."""
    DECK  = "deck"
    HAND  = "hand"
    FIELD = "field"
    LIFE  = "life"
    TRASH = "trash"


class PlayerID(Enum):
    P1 = "P1"
    P2 = "P2"

    def opponent(self) -> "PlayerID":
        return PlayerID.P2 if self == PlayerID.P1 else PlayerID.P1


class WinReason(Enum):
    """Reason the game ended. Set on GameState when transitioning to GAME_OVER."""
    LIFE_AND_LEADER_HIT = "life_and_leader_hit"   # rule 1-2-1-1-1
    DECK_OUT            = "deck_out"              # rule 1-2-1-1-2
    CONCESSION          = "concession"            # rule 1-2-3 (not used in MVP)
    CARD_EFFECT         = "card_effect"           # rule 1-2-5 (not used in MVP, no DSL)


# ── Card-level types ───────────────────────────────────────────────────────────

@dataclass(frozen=True)
class TempKeyword:
    """
    A keyword granted to a card temporarily (e.g. Kaido gives himself [Rush]
    during the turn he was played).
    Removed when the game advances past `expires_after`.
    """
    keyword:       str    # "Rush", "Blocker", "Double Attack", etc.
    expires_after: Phase  # the engine removes this once the phase has passed


@dataclass(frozen=True)
class CardInstance:
    """
    One physical card in the game.  There are 51 per player (50-card deck + 1 leader).

    instance_id  — unique within the game, e.g. "p1-0", "p1-1" ... "p2-50"
    definition_id — points to the card database, e.g. "ST01-001"

    The engine looks up definition_id in the card DB to get base power,
    cost, effect text, keywords[], triggers[], etc.
    CardInstance itself only holds *runtime* state (zone, rested, attached Don, etc.)
    """
    instance_id:             str
    definition_id:           str
    zone:                    Zone
    controller:              PlayerID
    rested:                  bool = False
    attached_don:            int  = 0
    temp_keywords:           tuple[TempKeyword, ...] = ()
    # Set by effects like Nami's [On Play] — card cannot attack until the phase passes
    attack_restricted_until: Optional[Phase] = None

    def has_temp_keyword(self, kw: str) -> bool:
        """Check temporary keyword grants only (base keywords live in the card DB)."""
        return any(tk.keyword == kw for tk in self.temp_keywords)


# ── DON!! field ────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class DonField:
    """
    DON!! cards currently on the field, split into active and rested counts.
    We store counts (not instances) because Don cards are fungible —
    they have no individual identity.
    """
    active: int = 0
    rested: int = 0

    @property
    def total(self) -> int:
        return self.active + self.rested


# ── Temporary power effects ────────────────────────────────────────────────────

@dataclass(frozen=True)
class TempEffect:
    """
    A time-scoped power modifier on a specific card.

    Examples:
      - Scalpel gives +2000 power until end of battle  (expires_after=BATTLE_CLEANUP)
      - A [Your Turn] leader ability that buffs all your characters
        would have expires_after=END (removed at end of turn)

    The state sweep in step() removes TempEffects once their phase has passed.
    """
    target_instance_id: str
    power_modifier:     int   = 0
    expires_after:      Phase = Phase.BATTLE_CLEANUP


# ── Effect stack ───────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class StackEntry:
    """
    One entry on the effect resolution stack (LIFO order).

    `effect` is a DSL node — a plain dict matching the schema defined in
    the DSL layer (e.g. {"type": "KO"} or {"type": "Sequence", "effects": [...]}).
    GameState itself has no knowledge of what these dicts mean —
    that interpretation lives in engine/resolver.py.

    `targets` starts as None and is bound once the player (or engine)
    resolves target selection.
    """
    effect:             dict                         # DSL node — opaque to GameState
    source_instance_id: str                          # which card produced this effect
    controller:         PlayerID                     # who controls the effect
    targets:            Optional[tuple[str, ...]] = None  # bound instance_ids


# ── Player input request ───────────────────────────────────────────────────────

@dataclass(frozen=True)
class InputRequest:
    """
    When the engine needs a player decision it cannot make itself —
    target selection, "you may" choices, blocker decisions — it halts and
    writes this onto GameState.pending_input.

    The next call to step() MUST be a RespondInput action carrying the answer.
    Any other action is rejected while pending_input is set.

    `resume_context` is opaque data the engine uses to know where to pick up
    after the answer arrives (e.g. which stack entry was waiting for targets).
    """
    request_type:   str                       # "ChooseTargets" | "YesNo" | "ChooseCards"
    prompt:         str                       # shown in the UI and RL observation
    valid_choices:  tuple[str, ...]           # instance_ids, or ("yes", "no")
    min_choices:    int = 0                   # 0 means "up to" (optional)
    max_choices:    int = 1
    resume_context: Optional[dict] = None     # opaque engine bookkeeping


# ── Battle context ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class BattleContext:
    """
    Exists only during the battle sub-phases (BATTLE_DECLARED through BATTLE_CLEANUP).
    Cleared (set to None on GameState) when BATTLE_CLEANUP finishes.
    """
    attacker_id:  str
    target_id:    str
    power_boosts: tuple[int, ...] = ()   # accumulated from Counter cards this battle


# ── Player state ───────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class PlayerState:
    """
    Everything about one player's side of the board.

    All zones are tuples (immutable sequences).
    For ordered zones: index 0 = top.
      - deck[0]  is the card you'd draw next
      - life[0]  is the life card that would be revealed if the leader is hit

    `once_per_turn_used` tracks which [Once Per Turn] abilities have fired
    this turn.  Cleared during the REFRESH phase.
    """
    player_id:          PlayerID
    leader:             CardInstance
    hand:               tuple[CardInstance, ...]
    deck:               tuple[CardInstance, ...]   # [0] = top
    field:              tuple[CardInstance, ...]
    life:               tuple[CardInstance, ...]   # [0] = top (revealed when leader is hit)
    trash:              tuple[CardInstance, ...]
    don_deck_count:     int                        # Don cards remaining (starts at 10)
    don_field:          DonField
    once_per_turn_used: frozenset[str]             # instance_ids of OPT abilities used

    @property
    def life_count(self) -> int:
        return len(self.life)

    @property
    def hand_count(self) -> int:
        return len(self.hand)

    def all_cards(self) -> tuple[CardInstance, ...]:
        """Every CardInstance this player owns, across all zones."""
        return (self.leader,) + self.hand + self.deck + self.field + self.life + self.trash


# ── Root GameState ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class GameState:
    """
    Complete, self-contained snapshot of the game at one moment.

    This is the object that flows through the entire system:
      - The RL agent reads it to produce observations and rewards
      - The UI diffs two consecutive states to produce animations
      - The replay system stores (initial_state, seed, [actions]) and re-runs
      - Tests assert on specific fields to verify engine behaviour

    Never modify this directly.  Use dataclasses.replace(state, field=new_value)
    to produce a new snapshot with one field changed.
    """
    turn_number:      int
    active_player_id: PlayerID
    phase:            Phase
    p1:               PlayerState
    p2:               PlayerState
    effect_stack:     tuple[StackEntry, ...]
    pending_input:    Optional[InputRequest]
    temp_effects:     tuple[TempEffect, ...]
    battle_context:   Optional[BattleContext]
    rng_state:        int           # advances each time the engine needs randomness
    ruleset_id:       str           # e.g. "ST01-ST04-v1" — for future errata support
    winner:           Optional[PlayerID] = None
    win_reason:       Optional[WinReason] = None

    # ── Convenience accessors ──────────────────────────────────────────────

    def active_player(self) -> PlayerState:
        return self.p1 if self.active_player_id == PlayerID.P1 else self.p2

    def inactive_player(self) -> PlayerState:
        return self.p2 if self.active_player_id == PlayerID.P1 else self.p1

    def get_player(self, pid: PlayerID) -> PlayerState:
        return self.p1 if pid == PlayerID.P1 else self.p2

    def get_card(self, instance_id: str) -> Optional[CardInstance]:
        """Find any card by instance_id across both players and all zones."""
        for player in (self.p1, self.p2):
            for card in player.all_cards():
                if card.instance_id == instance_id:
                    return card
        return None

    def is_waiting_for_input(self) -> bool:
        """True if step() is paused — next action must be RespondInput."""
        return self.pending_input is not None

    def is_terminal(self) -> bool:
        return self.phase == Phase.GAME_OVER


# ── Invariant checker ──────────────────────────────────────────────────────────

def validate_invariants(state: GameState) -> None:
    """
    Assert fundamental truths about any valid GameState.
    Call this after every step() in tests and debug mode.
    If this raises, the engine produced a structurally broken state.

    This does NOT check game rules (e.g. "was that KO legal?") —
    just structural integrity.
    """
    # 1. Every instance_id across the whole game must be unique
    all_ids: list[str] = []
    for player in (state.p1, state.p2):
        for card in player.all_cards():
            all_ids.append(card.instance_id)
    assert len(all_ids) == len(set(all_ids)), \
        f"Duplicate instance_ids found: {[x for x in all_ids if all_ids.count(x) > 1]}"

    # 2. Each player must have exactly 51 cards total (50 deck + 1 leader)
    for player in (state.p1, state.p2):
        total = len(player.all_cards())
        assert total == 51, \
            f"Player {player.player_id} has {total} cards, expected 51"

    # 3. Don counts must be non-negative
    for player in (state.p1, state.p2):
        assert player.don_deck_count >= 0, \
            f"Player {player.player_id} has negative don_deck_count"
        assert player.don_field.active >= 0 and player.don_field.rested >= 0, \
            f"Player {player.player_id} has negative don_field counts"
        assert player.don_field.total <= 10, \
            f"Player {player.player_id} has more than 10 Don on field"

    # 4. Life count must be 0–5
    for player in (state.p1, state.p2):
        assert 0 <= player.life_count <= 5, \
            f"Player {player.player_id} has {player.life_count} life cards (expected 0–5)"

    # 5. If game is over, winner and win_reason must be set
    if state.phase == Phase.GAME_OVER:
        assert state.winner is not None, "GAME_OVER phase but winner is None"
        assert state.win_reason is not None, "GAME_OVER phase but win_reason is None"

    # 6. If pending_input is set, effect_stack must be non-empty
    if state.pending_input is not None:
        assert len(state.effect_stack) > 0, \
            "pending_input is set but effect_stack is empty"

    # 7. Battle context must exist iff we are in a battle sub-phase
    battle_phases = {
        Phase.BATTLE_DECLARED, Phase.BATTLE_WHEN_ATK, Phase.BATTLE_BLOCKER,
        Phase.BATTLE_COUNTER,  Phase.BATTLE_DAMAGE,   Phase.BATTLE_TRIGGER,
        Phase.BATTLE_CLEANUP,
    }
    if state.phase in battle_phases:
        assert state.battle_context is not None, \
            f"In phase {state.phase} but battle_context is None"
    else:
        assert state.battle_context is None, \
            f"battle_context is set but phase is {state.phase}"
