import dataclasses
import pytest
from engine.card_db import CardDB
from engine.game_state import PlayerID, StackEntry, Zone
from engine.dsl.resolver import resolve_top
from tests.test_game_state import make_state, make_card


@pytest.fixture(scope="module")
def db():
    return CardDB()


def test_resolve_top_empty_stack_is_noop(db):
    state = make_state()
    out = resolve_top(state, db)
    assert out == state


def test_resolve_top_simple_draw_completes_and_pops(db):
    state = make_state()
    pre_hand = len(state.p1.hand)
    entry = StackEntry(
        effect={"type": "Draw", "count": 2},
        source_instance_id="p1-leader",
        controller=PlayerID.P1,
        initial_state_ref=state,
    )
    state = dataclasses.replace(state, effect_stack=(entry,))
    out = resolve_top(state, db)
    assert len(out.effect_stack) == 0
    assert len(out.p1.hand) == pre_hand + 2


def test_resolve_top_with_choice_sets_pending_input_and_keeps_entry(db):
    state = make_state()
    char = make_card("p2-c1", "ST01-002", Zone.FIELD, PlayerID.P2)
    new_p2 = dataclasses.replace(state.p2, field=(char,))
    state = dataclasses.replace(state, p2=new_p2)
    entry = StackEntry(
        effect={"type": "KO", "target": {"controller": "opponent", "type": "Character"},
                "max_choices": 1},
        source_instance_id="p1-leader",
        controller=PlayerID.P1,
        initial_state_ref=state,
    )
    state = dataclasses.replace(state, effect_stack=(entry,))
    out = resolve_top(state, db)
    assert out.pending_input is not None
    assert "p2-c1" in out.pending_input.valid_choices
    assert len(out.effect_stack) == 1


def test_resolve_with_input_completes(db):
    state = make_state()
    char = make_card("p2-c1", "ST01-002", Zone.FIELD, PlayerID.P2)
    new_p2 = dataclasses.replace(state.p2, field=(char,))
    state = dataclasses.replace(state, p2=new_p2)
    initial = state
    entry = StackEntry(
        effect={"type": "KO", "target": {"controller": "opponent", "type": "Character"},
                "max_choices": 1},
        source_instance_id="p1-leader",
        controller=PlayerID.P1,
        inputs_collected=(("p2-c1",),),
        initial_state_ref=initial,
    )
    state = dataclasses.replace(state, effect_stack=(entry,))
    out = resolve_top(state, db)
    assert out.pending_input is None
    assert len(out.effect_stack) == 0
    assert len(out.p2.field) == 0


def test_respond_input_appends_to_top_entry_and_resolves(db):
    """T11: RespondInput in non-SETUP phase appends to top stack entry and re-resolves."""
    from engine.actions import RespondInput
    from engine.step import step

    state = make_state()
    char = make_card("p2-c1", "ST01-002", Zone.FIELD, PlayerID.P2)
    new_p2 = dataclasses.replace(state.p2, field=(char,))
    state = dataclasses.replace(state, p2=new_p2)

    entry = StackEntry(
        effect={"type": "KO", "target": {"controller": "opponent", "type": "Character"},
                "max_choices": 1},
        source_instance_id="p1-leader",
        controller=PlayerID.P1,
        initial_state_ref=state,
    )
    state = dataclasses.replace(state, effect_stack=(entry,))
    state = resolve_top(state, db)
    assert state.pending_input is not None

    state = step(state, RespondInput(choices=("p2-c1",)), db)

    assert state.pending_input is None
    assert len(state.effect_stack) == 0
    assert len(state.p2.field) == 0
