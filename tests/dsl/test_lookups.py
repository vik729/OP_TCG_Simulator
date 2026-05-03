import dataclasses
import pytest
from engine.game_state import ScopedEffect, PlayerID, Zone
from engine.dsl.lookups import power_modifiers, granted_keywords
from tests.test_game_state import make_state, make_card


def test_power_modifiers_sums_active_modifications():
    state = make_state()
    state = dataclasses.replace(state, scoped_effects=(
        ScopedEffect(target_instance_id="p1-leader",
                     modification={"type": "PowerMod", "amount": 1000}),
        ScopedEffect(target_instance_id="p1-leader",
                     modification={"type": "PowerMod", "amount": -500}),
        ScopedEffect(target_instance_id="p2-leader",
                     modification={"type": "PowerMod", "amount": 9999}),
    ))
    assert power_modifiers(state, "p1-leader") == 500


def test_power_modifiers_ignores_non_powermod():
    state = make_state()
    state = dataclasses.replace(state, scoped_effects=(
        ScopedEffect(target_instance_id="p1-leader",
                     modification={"type": "KeywordGrant", "keyword": "Rush"}),
    ))
    assert power_modifiers(state, "p1-leader") == 0


def test_power_modifiers_respects_applies_when_your_turn():
    state = make_state()  # active=P1
    state = dataclasses.replace(state, scoped_effects=(
        ScopedEffect(target_instance_id="p1-leader",
                     modification={"type": "PowerMod", "amount": 1000},
                     applies_when="your_turn"),
    ))
    assert power_modifiers(state, "p1-leader") == 1000
    state2 = dataclasses.replace(state, active_player_id=PlayerID.P2)
    assert power_modifiers(state2, "p1-leader") == 0


def test_power_modifiers_respects_applies_when_opponent_turn():
    state = make_state()  # active=P1
    state = dataclasses.replace(state, scoped_effects=(
        ScopedEffect(target_instance_id="p1-leader",
                     modification={"type": "PowerMod", "amount": 1000},
                     applies_when="opponent_turn"),
    ))
    # P1's turn — buff is on P1's card; opponent_turn means it's NOT P1's turn
    assert power_modifiers(state, "p1-leader") == 0
    state2 = dataclasses.replace(state, active_player_id=PlayerID.P2)
    assert power_modifiers(state2, "p1-leader") == 1000


def test_granted_keywords_returns_active_keywords():
    state = make_state()
    state = dataclasses.replace(state, scoped_effects=(
        ScopedEffect(target_instance_id="p1-leader",
                     modification={"type": "KeywordGrant", "keyword": "Rush"}),
        ScopedEffect(target_instance_id="p1-leader",
                     modification={"type": "KeywordGrant", "keyword": "Banish"}),
    ))
    assert granted_keywords(state, "p1-leader") == frozenset({"Rush", "Banish"})
