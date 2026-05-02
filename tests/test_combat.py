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


class TestAttachedDonPowerBoost:
    """Rule 6-5-5-2: attached DON adds 1000 power *during the controller's turn*."""

    def test_attached_don_does_not_boost_on_opponent_turn(self, db):
        """P1 attacks P2's leader (5000). P2's leader has 2 attached DON.
        P1's turn -> defender's DON gives 0 boost. 5000 vs 5000 -> HIT (tie)."""
        life_card = make_card("p2-life-0", "ST01-002", Zone.LIFE, PlayerID.P2)
        ctx = BattleContext(attacker_id="p1-leader", target_id="p2-leader")
        state = make_state(
            phase=Phase.BATTLE_DAMAGE,
            battle_context=ctx,
            active_player_id=PlayerID.P1,
        )
        boosted_defender_leader = dataclasses.replace(state.p2.leader, attached_don=2)
        new_p2 = dataclasses.replace(state.p2, life=(life_card,),
                                     leader=boosted_defender_leader)
        state = dataclasses.replace(state, p2=new_p2)

        new_state = advance_battle(state, db)
        assert len(new_state.p2.life) == 0, \
            "Defender's attached DON wrongly boosted on opponent turn — leader survived a tie"
        assert len(new_state.p2.hand) == 1, "Life card should move to hand on hit"

    def test_attached_don_boosts_on_controller_turn(self, db):
        """Attacker's own DON does boost during their turn.
        P1 leader (5000) + 1 attached DON = 6000 vs P2 leader 5000 -> HIT."""
        life_card = make_card("p2-life-0", "ST01-002", Zone.LIFE, PlayerID.P2)
        ctx = BattleContext(attacker_id="p1-leader", target_id="p2-leader")
        state = make_state(
            phase=Phase.BATTLE_DAMAGE,
            battle_context=ctx,
            active_player_id=PlayerID.P1,
        )
        boosted_attacker = dataclasses.replace(state.p1.leader, attached_don=1)
        new_p1 = dataclasses.replace(state.p1, leader=boosted_attacker)
        new_p2 = dataclasses.replace(state.p2, life=(life_card,))
        state = dataclasses.replace(state, p1=new_p1, p2=new_p2)

        new_state = advance_battle(state, db)
        assert len(new_state.p2.life) == 0

    def test_counter_boosts_target_regardless_of_turn(self, db):
        """Counter cards boost the defender's power; this is independent of
        the DON-during-your-turn rule. P1 leader 5000 vs P2 leader 5000 + 2000
        counter = 7000 -> MISS."""
        life_card = make_card("p2-life-0", "ST01-002", Zone.LIFE, PlayerID.P2)
        ctx = BattleContext(
            attacker_id="p1-leader", target_id="p2-leader",
            power_boosts=(2000,),
        )
        state = make_state(
            phase=Phase.BATTLE_DAMAGE,
            battle_context=ctx,
            active_player_id=PlayerID.P1,
        )
        new_p2 = dataclasses.replace(state.p2, life=(life_card,))
        state = dataclasses.replace(state, p2=new_p2)

        new_state = advance_battle(state, db)
        assert len(new_state.p2.life) == 1, "Counter should have made attack MISS"
