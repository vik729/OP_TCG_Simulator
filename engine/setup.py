"""
engine/setup.py
===============
Initial state builder + SETUP-phase action handlers.

The setup procedure runs through the normal step() loop:

  Phase.SETUP, ChooseFirst("P1") -> shuffle decks, deal 5, P1 mulligan input
  Phase.SETUP, RespondInput(...) -> process P1 mulligan, P2 mulligan input
  Phase.SETUP, RespondInput(...) -> process P2 mulligan, deal life cards,
                                    transition to REFRESH (turn=1)
"""
from __future__ import annotations
import dataclasses
from engine.game_state import (
    GameState, PlayerState, CardInstance, DonField, Phase, Zone,
    PlayerID, InputRequest, validate_invariants,
)
from engine.card_db import CardDB
from engine.ruleset import Ruleset
from engine.deck import DeckList
from engine.rng import split_rng
from engine.actions import ChooseFirst, RespondInput


def _build_player(deck: DeckList, pid: PlayerID, db: CardDB) -> PlayerState:
    """Build a PlayerState from a DeckList. Cards are placed in DECK zone in
    decklist order - pre-shuffle. Instance ids: p{N}-leader and p{N}-{0..49}.
    """
    prefix = "p1" if pid == PlayerID.P1 else "p2"
    leader = CardInstance(
        instance_id=f"{prefix}-leader",
        definition_id=deck.leader_id,
        zone=Zone.FIELD,
        controller=pid,
    )
    deck_cards = tuple(
        CardInstance(
            instance_id=f"{prefix}-{i}",
            definition_id=cid,
            zone=Zone.DECK,
            controller=pid,
        )
        for i, cid in enumerate(deck.main_deck_ids)
    )
    return PlayerState(
        player_id=pid,
        leader=leader,
        hand=(),
        deck=deck_cards,
        field=(),
        life=(),
        trash=(),
        don_deck_count=10,
        don_field=DonField(active=0, rested=0),
        once_per_turn_used=frozenset(),
    )


def build_initial_state(p1_deck: DeckList, p2_deck: DeckList, seed: int,
                        ruleset: Ruleset, db: CardDB) -> GameState:
    """Construct the pre-game state. Returns a GameState in Phase.SETUP awaiting
    a ChooseFirst action."""
    state = GameState(
        turn_number=0,
        active_player_id=PlayerID.P1,   # placeholder; ChooseFirst overrides
        phase=Phase.SETUP,
        p1=_build_player(p1_deck, PlayerID.P1, db),
        p2=_build_player(p2_deck, PlayerID.P2, db),
        effect_stack=(),
        pending_input=None,
        scoped_effects=(),
        battle_context=None,
        rng_state=seed,
        ruleset_id=ruleset.id,
        winner=None,
        win_reason=None,
    )
    validate_invariants(state)
    return state


def _shuffle_player_deck(player: PlayerState, rng) -> PlayerState:
    deck_list = list(player.deck)
    rng.shuffle(deck_list)
    return dataclasses.replace(player, deck=tuple(deck_list))


def _deal_n(player: PlayerState, n: int) -> PlayerState:
    drawn = tuple(
        dataclasses.replace(c, zone=Zone.HAND) for c in player.deck[:n]
    )
    return dataclasses.replace(
        player,
        deck=player.deck[n:],
        hand=player.hand + drawn,
    )


def _deal_life(player: PlayerState, life_value: int) -> PlayerState:
    """Place `life_value` cards from top of deck face-down in life area.

    Per rule 5-2-1-7: top of deck -> bottom of life. Reverse so deck-top
    becomes life-bottom (life[-1] = deck[0]).
    """
    life_cards = tuple(
        dataclasses.replace(c, zone=Zone.LIFE) for c in player.deck[:life_value]
    )
    life_in_correct_order = tuple(reversed(life_cards))
    return dataclasses.replace(
        player,
        deck=player.deck[life_value:],
        life=life_in_correct_order,
    )


def handle_choose_first(state: GameState, action: ChooseFirst, db: CardDB) -> GameState:
    """Handle ChooseFirst: set active_player_id, shuffle both decks, deal 5
    to each, create pending_input for P1's mulligan."""
    first_player = PlayerID(action.first_player_id)

    rng, new_rng_state = split_rng(state.rng_state)
    p1 = _shuffle_player_deck(state.p1, rng)
    p2 = _shuffle_player_deck(state.p2, rng)
    p1 = _deal_n(p1, 5)
    p2 = _deal_n(p2, 5)

    pending = InputRequest(
        request_type="YesNo",
        prompt="Mulligan? (yes/no)",
        valid_choices=("yes", "no"),
        min_choices=1,
        max_choices=1,
        resume_context={"step": "p1_mulligan"},
    )

    return dataclasses.replace(
        state,
        active_player_id=first_player,
        p1=p1,
        p2=p2,
        rng_state=new_rng_state,
        pending_input=pending,
    )


def _maybe_mulligan(state: GameState, player: PlayerState, take: bool) -> tuple[PlayerState, int]:
    """If taking the mulligan, return hand to deck, reshuffle, deal 5 again.
    Returns (new_player, new_rng_state)."""
    if not take:
        return player, state.rng_state
    rng, new_rng_state = split_rng(state.rng_state)
    deck_combined = list(player.deck) + [
        dataclasses.replace(c, zone=Zone.DECK) for c in player.hand
    ]
    rng.shuffle(deck_combined)
    new_deck = tuple(deck_combined)
    drawn = tuple(
        dataclasses.replace(c, zone=Zone.HAND) for c in new_deck[:5]
    )
    new_player = dataclasses.replace(
        player,
        deck=new_deck[5:],
        hand=drawn,
    )
    return new_player, new_rng_state


def handle_setup_respond_input(state: GameState, action: RespondInput,
                               db: CardDB) -> GameState:
    """Handle a RespondInput during SETUP - either mulligan answer."""
    pending = state.pending_input
    assert pending is not None, "handle_setup_respond_input called without pending_input"
    step = pending.resume_context.get("step") if pending.resume_context else None
    answer = action.choices[0] if action.choices else "no"

    if step == "p1_mulligan":
        new_p1, new_rng_state = _maybe_mulligan(state, state.p1, take=(answer == "yes"))
        new_pending = InputRequest(
            request_type="YesNo",
            prompt="Mulligan? (yes/no)",
            valid_choices=("yes", "no"),
            min_choices=1, max_choices=1,
            resume_context={"step": "p2_mulligan"},
        )
        return dataclasses.replace(
            state, p1=new_p1, pending_input=new_pending,
            rng_state=new_rng_state,
        )

    elif step == "p2_mulligan":
        new_p2, new_rng_state = _maybe_mulligan(state, state.p2, take=(answer == "yes"))
        # All mulligans done. Deal life cards and transition to REFRESH.
        p1_leader_def = db.get(state.p1.leader.definition_id)
        p2_leader_def = db.get(new_p2.leader.definition_id)
        p1_with_life = _deal_life(state.p1, p1_leader_def.life or 0)
        p2_with_life = _deal_life(new_p2, p2_leader_def.life or 0)

        return dataclasses.replace(
            state,
            p1=p1_with_life,
            p2=p2_with_life,
            phase=Phase.REFRESH,
            turn_number=1,
            pending_input=None,
            rng_state=new_rng_state,
        )

    raise ValueError(f"Unknown SETUP resume step: {step}")
