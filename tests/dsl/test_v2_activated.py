import dataclasses
import pytest
from engine.card_db import CardDB
from engine.game_state import Phase, PlayerID, Zone, DonField
from engine.actions import ActivateAbility
from engine.step import step, IllegalActionError
from tests.test_game_state import make_state, make_card


@pytest.fixture
def db():
    return CardDB()


def _make_field_char(state, db, monkeypatch, triggers):
    char = make_card("p1-c1", "ST01-002", Zone.FIELD, PlayerID.P1)
    state = dataclasses.replace(state, p1=dataclasses.replace(state.p1, field=(char,),
                                                              don_field=DonField(active=2, rested=0)))
    monkeypatch.setitem(db._cards, "ST01-002",
                        dataclasses.replace(db._cards["ST01-002"], triggers=triggers,
                                            dsl_status="parsed"))
    return state


def test_activate_ability_pays_cost_and_runs_effect(db, monkeypatch):
    triggers = ({"on": "ActivateMain", "once_per_turn": True,
                 "cost": [{"type": "RestSelf"}, {"type": "RestDon", "amount": 1}],
                 "effect": {"type": "Draw", "count": 1}},)
    state = _make_field_char(make_state(turn_number=2), db, monkeypatch, triggers)
    pre_hand = len(state.p1.hand)
    new_state = step(state, ActivateAbility(card_instance_id="p1-c1", trigger_index=0), db)
    assert new_state.get_card("p1-c1").rested is True
    assert new_state.p1.don_field.active == 1
    assert new_state.p1.don_field.rested == 1
    assert len(new_state.p1.hand) == pre_hand + 1
    assert "p1-c1" in new_state.p1.once_per_turn_used


def test_activate_ability_aborts_on_cost_failure(db, monkeypatch):
    triggers = ({"on": "ActivateMain",
                 "cost": [{"type": "RestDon", "amount": 99}],
                 "effect": {"type": "Draw", "count": 1}},)
    state = _make_field_char(make_state(turn_number=2), db, monkeypatch, triggers)
    with pytest.raises(IllegalActionError):
        step(state, ActivateAbility(card_instance_id="p1-c1", trigger_index=0), db)


def test_opt_blocks_second_activation(db, monkeypatch):
    triggers = ({"on": "ActivateMain", "once_per_turn": True,
                 "effect": {"type": "Draw", "count": 1}},)
    state = _make_field_char(make_state(turn_number=2), db, monkeypatch, triggers)
    state = dataclasses.replace(state, p1=dataclasses.replace(
        state.p1, once_per_turn_used=frozenset({"p1-c1"})))
    with pytest.raises(IllegalActionError, match="once per turn"):
        step(state, ActivateAbility(card_instance_id="p1-c1", trigger_index=0), db)


def test_legal_actions_includes_activate_ability(db, monkeypatch):
    from engine.legal_actions import legal_actions
    triggers = ({"on": "ActivateMain", "once_per_turn": True,
                 "cost": [{"type": "RestSelf"}],
                 "effect": {"type": "Draw", "count": 1}},)
    state = _make_field_char(make_state(turn_number=2), db, monkeypatch, triggers)
    actions = legal_actions(state, db)
    aa = [a for a in actions if isinstance(a, ActivateAbility)]
    assert len(aa) == 1
    assert aa[0].card_instance_id == "p1-c1"
    assert aa[0].trigger_index == 0
