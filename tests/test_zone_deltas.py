"""Per-action zone-delta envelope tests.

For every step of a random game, assert that the change in each
player's hand/life size and DON totals stays inside the envelope of
deltas the action could legally produce. Also asserts the always-true
DON conservation invariant: don_deck + don_field + sum(attached) == 10
for each player at every moment.

These exist to catch the kind of bug where a card silently disappears
or appears in a zone — e.g. "I played a counter but my hand size
didn't go down".
"""
import random
import pytest
from hypothesis import given, settings, strategies as st
from engine.card_db import CardDB
from engine.deck import load_official_deck
from engine.ruleset import RULESETS
from engine.setup import build_initial_state
from engine.step import step
from engine.bots.random_bot import random_legal_action
from engine.game_state import Phase, PlayerID, GameState
from engine.actions import AdvancePhase, PlayCard, PlayCounter


@pytest.fixture(scope="module")
def db():
    return CardDB()


@pytest.fixture(scope="module")
def ruleset():
    return RULESETS["ST01-ST04-v1"]


def _allowed_hand_delta(action, prev: GameState, pid: PlayerID) -> set[int]:
    """Hand-size deltas that a single action may produce for player `pid`."""
    actor = prev.active_player_id
    if isinstance(action, AdvancePhase):
        if prev.phase == Phase.DRAW:
            return {0, 1} if pid == actor else {0}
        if prev.phase == Phase.BATTLE_DAMAGE:
            # Defender hand grows by `damage` on leader hit (no Banish).
            # Damage is 0 (miss/KO/banish), 1, or 2 (Double Attack).
            return {0, 1, 2}
        return {0}
    if isinstance(action, PlayCard):
        return {-1} if pid == actor else {0}
    if isinstance(action, PlayCounter):
        return {-1} if pid != actor else {0}
    return {0}


def _allowed_life_delta(action, prev: GameState, pid: PlayerID) -> set[int]:
    """Life-size deltas. Vanilla: only leader hits remove life cards."""
    if isinstance(action, AdvancePhase) and prev.phase == Phase.BATTLE_DAMAGE:
        return {0, -1, -2}
    return {0}


def _don_total(player) -> int:
    """Total DON owned: deck + cost area + attached to leader/field."""
    attached = (player.leader.attached_don
                + sum(c.attached_don for c in player.field))
    return (player.don_deck_count
            + player.don_field.active
            + player.don_field.rested
            + attached)


def _run_game(seed: int, db, ruleset):
    """Yield (prev_state, action, post_state) for every step until terminal."""
    p1 = load_official_deck("ST-01", db)
    p2 = load_official_deck("ST-02", db)
    state = build_initial_state(p1, p2, seed=seed, ruleset=ruleset, db=db)
    bot_rng = random.Random(seed + 100_000)
    while not state.is_terminal():
        action = random_legal_action(state, bot_rng, db)
        prev = state
        state = step(state, action, db)
        yield prev, action, state


@given(seed=st.integers(0, 1000))
@settings(max_examples=15, deadline=None)
def test_hand_delta_per_action(seed, db, ruleset):
    for prev, action, cur in _run_game(seed, db, ruleset):
        if prev.phase == Phase.SETUP:
            continue  # one-time bootstrap (deal hand, mulligan, deal life)
        for pid in (PlayerID.P1, PlayerID.P2):
            d = len(cur.get_player(pid).hand) - len(prev.get_player(pid).hand)
            allowed = _allowed_hand_delta(action, prev, pid)
            assert d in allowed, (
                f"hand[{pid.value}] changed by {d} (allowed {allowed}) "
                f"after {type(action).__name__} in phase {prev.phase.value} "
                f"at turn {prev.turn_number}"
            )


@given(seed=st.integers(0, 1000))
@settings(max_examples=15, deadline=None)
def test_life_delta_per_action(seed, db, ruleset):
    for prev, action, cur in _run_game(seed, db, ruleset):
        if prev.phase == Phase.SETUP:
            continue  # life cards dealt during setup; not a per-action event
        for pid in (PlayerID.P1, PlayerID.P2):
            d = len(cur.get_player(pid).life) - len(prev.get_player(pid).life)
            allowed = _allowed_life_delta(action, prev, pid)
            assert d in allowed, (
                f"life[{pid.value}] changed by {d} (allowed {allowed}) "
                f"after {type(action).__name__} in phase {prev.phase.value} "
                f"at turn {prev.turn_number}"
            )


@given(seed=st.integers(0, 1000))
@settings(max_examples=15, deadline=None)
def test_don_conserved(seed, db, ruleset):
    """Each player owns exactly 10 DON across deck+cost+attached, always."""
    for _, _, cur in _run_game(seed, db, ruleset):
        for pid in (PlayerID.P1, PlayerID.P2):
            total = _don_total(cur.get_player(pid))
            assert total == 10, (
                f"{pid.value} DON total = {total} (expected 10) "
                f"at turn {cur.turn_number} phase {cur.phase.value}"
            )


def test_counter_plus_leader_hit_reconciliation(db, ruleset):
    """Concrete case: defender plays a counter (-1 hand), then loses the
    battle (leader hit, +1 hand from life). Net hand change should be 0
    if both happen in the same battle. This is the scenario that produced
    the user's confusion in the seed-42 game."""
    # Just run seed 42 and verify per-action math holds — the hand delta
    # test above already enforces it. This test exists as documentation.
    for prev, action, cur in _run_game(42, db, ruleset):
        if prev.phase == Phase.SETUP:
            continue
        for pid in (PlayerID.P1, PlayerID.P2):
            d = len(cur.get_player(pid).hand) - len(prev.get_player(pid).hand)
            assert d in _allowed_hand_delta(action, prev, pid)
