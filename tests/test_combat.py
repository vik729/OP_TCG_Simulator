"""Tests for engine/combat.py - battle sub-phase machine."""
import pytest
import dataclasses
from engine.card_db import CardDB
from engine.game_state import (
    Phase, PlayerID, CardInstance, Zone, BattleContext, DonField, WinReason,
)
from engine.actions import (
    DeclareAttack, AdvancePhase, DeclareBlocker, PassBlocker,
    PlayCounter, PassCounter, PassTrigger,
)
from engine.combat import (
    begin_attack, advance_battle, handle_blocker, handle_pass_blocker,
    handle_counter, handle_pass_counter, handle_pass_trigger,
)
from tests.test_game_state import make_state, make_player, make_card


@pytest.fixture(scope="module")
def db():
    return CardDB()


class TestBeginAttack:
    def test_main_to_battle_declared(self, db):
        state = make_state(phase=Phase.MAIN, turn_number=2)
        action = DeclareAttack(
            attacker_instance_id="p1-leader",
            target_instance_id="p2-leader",
        )
        new_state = begin_attack(state, action, db)
        assert new_state.phase == Phase.BATTLE_DECLARED
        assert new_state.battle_context is not None
        assert new_state.battle_context.attacker_id == "p1-leader"
        assert new_state.battle_context.target_id == "p2-leader"

    def test_attacker_is_rested(self, db):
        state = make_state(phase=Phase.MAIN, turn_number=2)
        action = DeclareAttack("p1-leader", "p2-leader")
        new_state = begin_attack(state, action, db)
        attacker = new_state.get_card("p1-leader")
        assert attacker is not None
        assert attacker.rested is True


class TestAdvanceBattleDeclared:
    def test_declared_to_when_atk(self, db):
        ctx = BattleContext(attacker_id="p1-leader", target_id="p2-leader")
        state = make_state(phase=Phase.BATTLE_DECLARED, battle_context=ctx)
        new_state = advance_battle(state, db)
        assert new_state.phase == Phase.BATTLE_WHEN_ATK


class TestAdvanceBattleWhenAtk:
    def test_when_atk_to_blocker(self, db):
        ctx = BattleContext(attacker_id="p1-leader", target_id="p2-leader")
        state = make_state(phase=Phase.BATTLE_WHEN_ATK, battle_context=ctx)
        new_state = advance_battle(state, db)
        assert new_state.phase == Phase.BATTLE_BLOCKER


class TestPassBlocker:
    def test_pass_blocker_advances(self, db):
        ctx = BattleContext(attacker_id="p1-leader", target_id="p2-leader")
        state = make_state(phase=Phase.BATTLE_BLOCKER, battle_context=ctx)
        new_state = handle_pass_blocker(state, PassBlocker(), db)
        assert new_state.phase == Phase.BATTLE_COUNTER


class TestPassCounter:
    def test_pass_counter_advances(self, db):
        ctx = BattleContext(attacker_id="p1-leader", target_id="p2-leader")
        state = make_state(phase=Phase.BATTLE_COUNTER, battle_context=ctx)
        new_state = handle_pass_counter(state, PassCounter(), db)
        assert new_state.phase == Phase.BATTLE_DAMAGE


class TestAdvanceBattleDamage:
    def test_damage_clears_battle_context_eventually(self, db):
        ctx = BattleContext(attacker_id="p1-leader", target_id="p2-leader")
        state = make_state(phase=Phase.BATTLE_DAMAGE, battle_context=ctx)
        new_state = advance_battle(state, db)
        assert new_state.phase in (Phase.BATTLE_TRIGGER, Phase.BATTLE_CLEANUP, Phase.GAME_OVER)


class TestAdvanceBattleCleanup:
    def test_cleanup_returns_to_main(self, db):
        ctx = BattleContext(attacker_id="p1-leader", target_id="p2-leader")
        state = make_state(phase=Phase.BATTLE_CLEANUP, battle_context=ctx)
        new_state = advance_battle(state, db)
        assert new_state.phase == Phase.MAIN
        assert new_state.battle_context is None
