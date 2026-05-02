"""Tests for engine/win_check.py - defeat condition detection."""
import dataclasses
from engine.win_check import check_win_conditions
from engine.game_state import (
    GameState, Phase, PlayerID, WinReason,
)
from tests.test_game_state import make_state, make_player


class TestNoWinCondition:
    def test_normal_state_unchanged(self):
        state = make_state()
        result = check_win_conditions(state)
        assert result.phase == Phase.MAIN
        assert result.winner is None
        assert result.win_reason is None


class TestDeckOut:
    def test_p1_empty_deck_loses(self):
        """If P1's deck has 0 cards, P1 loses with DECK_OUT."""
        p1 = make_player(PlayerID.P1)
        empty_p1 = dataclasses.replace(p1, deck=(), trash=p1.deck)
        state = make_state(p1=empty_p1)
        result = check_win_conditions(state)
        assert result.phase == Phase.GAME_OVER
        assert result.winner == PlayerID.P2
        assert result.win_reason == WinReason.DECK_OUT

    def test_p2_empty_deck_loses(self):
        p2 = make_player(PlayerID.P2)
        empty_p2 = dataclasses.replace(p2, deck=(), trash=p2.deck)
        state = make_state(p2=empty_p2)
        result = check_win_conditions(state)
        assert result.phase == Phase.GAME_OVER
        assert result.winner == PlayerID.P1
        assert result.win_reason == WinReason.DECK_OUT


class TestLifeAndLeaderHit:
    def test_zero_life_alone_does_not_trigger(self):
        """check_win_conditions should NOT trigger LIFE_AND_LEADER_HIT just on
        bare 0-life state - the leader hit signal comes from combat directly
        setting GAME_OVER + LIFE_AND_LEADER_HIT before this function runs."""
        p1 = make_player(PlayerID.P1)
        zero_life_p1 = dataclasses.replace(p1, life=())
        state = make_state(p1=zero_life_p1)
        result = check_win_conditions(state)
        assert result.phase == Phase.MAIN
        assert result.winner is None


class TestAlreadyOver:
    def test_game_over_state_unchanged(self):
        """If state is already GAME_OVER, check_win_conditions is a no-op."""
        state = make_state(phase=Phase.GAME_OVER, winner=PlayerID.P1,
                           win_reason=WinReason.DECK_OUT)
        result = check_win_conditions(state)
        assert result.phase == Phase.GAME_OVER
        assert result.winner == PlayerID.P1
        assert result.win_reason == WinReason.DECK_OUT
