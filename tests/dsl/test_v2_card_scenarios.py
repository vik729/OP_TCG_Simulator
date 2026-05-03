"""End-to-end scenario tests for v2 authored cards."""
import dataclasses
import pytest
from engine.card_db import CardDB
from engine.game_state import Phase, PlayerID, Zone, DonField
from engine.actions import ActivateAbility, RespondInput
from engine.step import step
from tests.test_game_state import make_state, make_card


@pytest.fixture
def db():
    return CardDB()


def test_st02_007_jewelry_bonney_costs_paid_and_search_runs(db):
    """Bonney activates: pays 1 DON + rests self, runs SearchDeck (Supernovas).
    With no Supernovas in P1's ST-01 deck, SearchDeck silently no-ops;
    cost is still paid. This validates ActivateMain + cost array + SearchDeck end-to-end."""
    state = make_state(turn_number=2)
    bonney = make_card("p1-bonney", "ST02-007", Zone.FIELD, PlayerID.P1)
    state = dataclasses.replace(state, p1=dataclasses.replace(
        state.p1, field=(bonney,), don_field=DonField(active=2, rested=0)))

    state = step(state, ActivateAbility(card_instance_id="p1-bonney", trigger_index=0), db)

    # Costs paid
    assert state.get_card("p1-bonney").rested is True
    assert state.p1.don_field.active == 1
    assert state.p1.don_field.rested == 1
    # SearchDeck completed (no Supernovas in deck = no eligible)
    assert state.pending_input is None
    assert len(state.effect_stack) == 0
    # No card was added to hand (no eligible candidates)
    assert len(state.p1.hand) == 0


def test_st02_007_jewelry_bonney_finds_supernovas_when_present(db):
    """When P1's deck top contains a Supernovas card, Bonney's effect
    pauses for the player to choose."""
    state = make_state(turn_number=2)
    # Inject a Supernovas card at top of deck. ST02 cards are all Supernovas.
    supernova_card = make_card("p1-deck-top", "ST02-005", Zone.DECK, PlayerID.P1)
    bonney = make_card("p1-bonney", "ST02-007", Zone.FIELD, PlayerID.P1)
    new_deck = (supernova_card,) + state.p1.deck
    state = dataclasses.replace(state, p1=dataclasses.replace(
        state.p1, field=(bonney,), deck=new_deck,
        don_field=DonField(active=2, rested=0)))

    state = step(state, ActivateAbility(card_instance_id="p1-bonney", trigger_index=0), db)

    assert state.pending_input is not None
    assert "p1-deck-top" in state.pending_input.valid_choices

    state = step(state, RespondInput(choices=("p1-deck-top",)), db)
    assert state.pending_input is None
    assert any(c.instance_id == "p1-deck-top" for c in state.p1.hand)
