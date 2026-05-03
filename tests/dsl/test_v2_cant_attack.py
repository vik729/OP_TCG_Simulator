import dataclasses
import pytest
from engine.card_db import CardDB
from engine.game_state import ScopedEffect, PlayerID, Zone
from engine.actions import DeclareAttack
from engine.legal_actions import legal_actions
from tests.test_game_state import make_state, make_card


@pytest.fixture
def db():
    return CardDB()


def test_cant_attack_removes_declare_attack_options(db):
    state = make_state(turn_number=2)
    char = dataclasses.replace(
        make_card("p1-c1", "ST01-005", Zone.FIELD, PlayerID.P1),
        rested=False,
    )
    state = dataclasses.replace(state, p1=dataclasses.replace(state.p1, field=(char,)),
                                scoped_effects=(
        ScopedEffect(target_instance_id="p1-c1",
                     modification={"type": "CantAttack"}),
    ))
    actions = legal_actions(state, db)
    da = [a for a in actions if isinstance(a, DeclareAttack)
          and a.attacker_instance_id == "p1-c1"]
    assert len(da) == 0


def test_no_cant_attack_allows_declare_attack(db):
    state = make_state(turn_number=2)
    char = dataclasses.replace(
        make_card("p1-c1", "ST01-005", Zone.FIELD, PlayerID.P1),
        rested=False,
    )
    state = dataclasses.replace(state, p1=dataclasses.replace(state.p1, field=(char,)))
    actions = legal_actions(state, db)
    da = [a for a in actions if isinstance(a, DeclareAttack)
          and a.attacker_instance_id == "p1-c1"]
    # ST01-005 (Jinbe) attacking opponent leader should be a valid option
    assert len(da) >= 1
