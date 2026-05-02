"""Tests for engine/legal_actions.py - action enumeration per phase."""
import pytest
import dataclasses
from engine.card_db import CardDB
from engine.deck import load_official_deck
from engine.ruleset import RULESETS
from engine.setup import build_initial_state, handle_choose_first
from engine.game_state import (
    Phase, PlayerID, CardInstance, Zone, DonField, BattleContext, WinReason,
)
from engine.actions import (
    ChooseFirst, AdvancePhase, RespondInput,
    PlayCard, AttachDon, EndTurn, DeclareAttack,
    DeclareBlocker, PassBlocker,
    PlayCounter, PassCounter,
    ActivateTrigger, PassTrigger,
)
from engine.legal_actions import legal_actions
from tests.test_game_state import make_state, make_player


@pytest.fixture(scope="module")
def db():
    return CardDB()


@pytest.fixture(scope="module")
def ruleset():
    return RULESETS["ST01-ST04-v1"]


class TestSetupLegalActions:
    def test_setup_offers_both_choose_first(self, db, ruleset):
        st01 = load_official_deck("ST-01", db)
        st02 = load_official_deck("ST-02", db)
        state = build_initial_state(st01, st02, seed=42, ruleset=ruleset, db=db)
        actions = legal_actions(state, db)
        ids = {a.first_player_id for a in actions if isinstance(a, ChooseFirst)}
        assert ids == {"P1", "P2"}


class TestPendingInputLegalActions:
    def test_only_respond_input_when_pending(self, db, ruleset):
        st01 = load_official_deck("ST-01", db)
        st02 = load_official_deck("ST-02", db)
        state = build_initial_state(st01, st02, seed=42, ruleset=ruleset, db=db)
        state = handle_choose_first(state, ChooseFirst("P1"), db)
        actions = legal_actions(state, db)
        assert all(isinstance(a, RespondInput) for a in actions)
        choices = {a.choices for a in actions}
        assert ("yes",) in choices and ("no",) in choices


class TestAutomaticPhases:
    def test_refresh_returns_advance_only(self):
        state = make_state(phase=Phase.REFRESH)
        actions = legal_actions(state, None)
        assert actions == (AdvancePhase(),)

    def test_draw_returns_advance_only(self):
        state = make_state(phase=Phase.DRAW)
        actions = legal_actions(state, None)
        assert actions == (AdvancePhase(),)

    def test_don_returns_advance_only(self):
        state = make_state(phase=Phase.DON)
        actions = legal_actions(state, None)
        assert actions == (AdvancePhase(),)

    def test_end_returns_advance_only(self):
        state = make_state(phase=Phase.END)
        actions = legal_actions(state, None)
        assert actions == (AdvancePhase(),)


class TestMainPhase:
    def test_main_includes_end_turn(self, db):
        state = make_state(phase=Phase.MAIN)
        actions = legal_actions(state, db)
        assert EndTurn() in actions

    def test_main_no_attack_on_turn_1(self, db):
        state = make_state(phase=Phase.MAIN, turn_number=1)
        actions = legal_actions(state, db)
        assert not any(isinstance(a, DeclareAttack) for a in actions)


class TestGameOver:
    def test_no_legal_actions(self, db):
        state = make_state(phase=Phase.GAME_OVER, winner=PlayerID.P1,
                           win_reason=WinReason.LIFE_AND_LEADER_HIT)
        actions = legal_actions(state, db)
        assert actions == ()


class TestBattlePhases:
    def test_battle_blocker_offers_pass(self, db):
        state = make_state(
            phase=Phase.BATTLE_BLOCKER,
            battle_context=BattleContext(attacker_id="p1-0", target_id="p2-leader"),
        )
        actions = legal_actions(state, db)
        assert PassBlocker() in actions

    def test_battle_counter_offers_pass(self, db):
        state = make_state(
            phase=Phase.BATTLE_COUNTER,
            battle_context=BattleContext(attacker_id="p1-0", target_id="p2-leader"),
        )
        actions = legal_actions(state, db)
        assert PassCounter() in actions

    def test_battle_trigger_offers_pass(self, db):
        state = make_state(
            phase=Phase.BATTLE_TRIGGER,
            battle_context=BattleContext(attacker_id="p1-0", target_id="p2-leader"),
        )
        actions = legal_actions(state, db)
        assert PassTrigger() in actions
