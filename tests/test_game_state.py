"""
tests/test_game_state.py
========================
Structural tests for GameState and the Phase Machine.

These tests do NOT test game rules (that belongs in test_step.py later).
They test that:
  1. All types can be constructed correctly
  2. validate_invariants() catches broken states
  3. Phase machine correctly classifies legal/illegal actions
  4. Convenience accessors return the right things

Run with:  pytest tests/test_game_state.py -v
"""
import pytest
import dataclasses
from engine.game_state import (
    Phase, Zone, PlayerID,
    TempKeyword, CardInstance, DonField, TempEffect,
    StackEntry, InputRequest, BattleContext, PlayerState, GameState,
    validate_invariants,
)
from engine.actions import (
    PlayCard, ActivateAbility, AttachDon, DeclareAttack, EndTurn,
    DeclareBlocker, PassBlocker, PlayCounter, PassCounter,
    ActivateTrigger, PassTrigger, RespondInput, ChooseFirst,
)
from engine.phase_machine import (
    is_automatic, is_legal_action, phase_has_passed,
    PHASE_ORDER, defending_player_phases,
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def make_card(instance_id: str, definition_id: str = "ST01-001",
              zone: Zone = Zone.DECK, controller: PlayerID = PlayerID.P1) -> CardInstance:
    return CardInstance(
        instance_id=instance_id,
        definition_id=definition_id,
        zone=zone,
        controller=controller,
    )


def make_player(pid: PlayerID, id_offset: int = 0) -> PlayerState:
    """
    Build a minimal valid PlayerState: 1 leader + 50 deck cards = 51 total.
    instance_ids are "p{1|2}-{n}" to avoid collisions between players.
    """
    prefix = f"p{1 if pid == PlayerID.P1 else 2}"
    leader = make_card(f"{prefix}-leader", "ST01-001", Zone.FIELD, pid)
    deck = tuple(
        make_card(f"{prefix}-{i}", "ST01-002", Zone.DECK, pid)
        for i in range(50)
    )
    return PlayerState(
        player_id=pid,
        leader=leader,
        hand=(),
        deck=deck,
        field=(),
        life=(),
        trash=(),
        don_deck_count=10,
        don_field=DonField(active=0, rested=0),
        once_per_turn_used=frozenset(),
    )


def make_state(**overrides) -> GameState:
    """
    Build a minimal valid GameState in MAIN phase, P1's turn.
    Pass keyword args to override any field.
    """
    base = GameState(
        turn_number=1,
        active_player_id=PlayerID.P1,
        phase=Phase.MAIN,
        p1=make_player(PlayerID.P1),
        p2=make_player(PlayerID.P2),
        effect_stack=(),
        pending_input=None,
        temp_effects=(),
        battle_context=None,
        rng_state=0,
        ruleset_id="ST01-ST04-v1",
    )
    return dataclasses.replace(base, **overrides)


# ── GameState construction ─────────────────────────────────────────────────────

class TestConstruction:
    def test_gamestate_is_frozen(self):
        state = make_state()
        with pytest.raises((AttributeError, TypeError)):
            state.turn_number = 99  # type: ignore

    def test_card_instance_is_frozen(self):
        card = make_card("p1-0")
        with pytest.raises((AttributeError, TypeError)):
            card.rested = True  # type: ignore

    def test_playerstate_all_cards_count(self):
        player = make_player(PlayerID.P1)
        assert len(player.all_cards()) == 51   # 50 deck + 1 leader

    def test_get_card_finds_across_players(self):
        state = make_state()
        card = state.get_card("p2-5")
        assert card is not None
        assert card.instance_id == "p2-5"

    def test_get_card_returns_none_for_unknown(self):
        state = make_state()
        assert state.get_card("does-not-exist") is None

    def test_active_player_accessor(self):
        state = make_state(active_player_id=PlayerID.P1)
        assert state.active_player().player_id == PlayerID.P1

    def test_inactive_player_accessor(self):
        state = make_state(active_player_id=PlayerID.P1)
        assert state.inactive_player().player_id == PlayerID.P2

    def test_is_waiting_for_input_false_by_default(self):
        assert not make_state().is_waiting_for_input()

    def test_is_waiting_for_input_true_when_set(self):
        req = InputRequest(
            request_type="YesNo",
            prompt="You may draw 1 card?",
            valid_choices=("yes", "no"),
        )
        # Need a non-empty stack too (invariant 6)
        entry = StackEntry(
            effect={"type": "Draw", "n": 1},
            source_instance_id="p1-leader",
            controller=PlayerID.P1,
        )
        state = make_state(pending_input=req, effect_stack=(entry,))
        assert state.is_waiting_for_input()

    def test_temp_keyword_on_card(self):
        kw = TempKeyword(keyword="Rush", expires_after=Phase.END)
        card = make_card("p1-0")
        card_with_rush = dataclasses.replace(card, temp_keywords=(kw,))
        assert card_with_rush.has_temp_keyword("Rush")
        assert not card_with_rush.has_temp_keyword("Blocker")

    def test_don_field_total(self):
        don = DonField(active=3, rested=2)
        assert don.total == 5

    def test_player_id_opponent(self):
        assert PlayerID.P1.opponent() == PlayerID.P2
        assert PlayerID.P2.opponent() == PlayerID.P1

    def test_win_reason_default_is_none(self):
        assert make_state().win_reason is None

    def test_win_reason_settable(self):
        from engine.game_state import WinReason
        state = make_state(phase=Phase.GAME_OVER, winner=PlayerID.P1,
                           win_reason=WinReason.LIFE_AND_LEADER_HIT)
        assert state.win_reason == WinReason.LIFE_AND_LEADER_HIT


# ── validate_invariants ────────────────────────────────────────────────────────

class TestInvariants:
    def test_valid_state_passes(self):
        validate_invariants(make_state())   # should not raise

    def test_duplicate_instance_id_fails(self):
        """If two cards share an instance_id, the state is broken."""
        p1 = make_player(PlayerID.P1)
        # Manually duplicate an instance_id by replacing a deck card
        bad_leader = dataclasses.replace(p1.leader, instance_id="p1-0")
        bad_p1 = dataclasses.replace(p1, leader=bad_leader)
        state = make_state(p1=bad_p1)
        with pytest.raises(AssertionError, match="Duplicate instance_ids"):
            validate_invariants(state)

    def test_wrong_card_count_fails(self):
        """Adding a card to hand without removing from deck breaks the 51-card rule."""
        p1 = make_player(PlayerID.P1)
        extra_card = make_card("p1-extra", zone=Zone.HAND, controller=PlayerID.P1)
        bad_p1 = dataclasses.replace(p1, hand=(extra_card,))
        state = make_state(p1=bad_p1)
        with pytest.raises(AssertionError, match="51"):
            validate_invariants(state)

    def test_negative_don_fails(self):
        p1 = make_player(PlayerID.P1)
        bad_p1 = dataclasses.replace(p1, don_deck_count=-1)
        state = make_state(p1=bad_p1)
        with pytest.raises(AssertionError, match="negative"):
            validate_invariants(state)

    def test_too_many_life_fails(self):
        p1 = make_player(PlayerID.P1)
        life_cards = tuple(
            make_card(f"p1-life-{i}", zone=Zone.LIFE, controller=PlayerID.P1)
            for i in range(6)   # 6 > max of 5
        )
        # Remove 6 deck cards to keep total at 51
        remaining_deck = p1.deck[6:]
        bad_p1 = dataclasses.replace(p1, life=life_cards, deck=remaining_deck)
        state = make_state(p1=bad_p1)
        with pytest.raises(AssertionError, match="life cards"):
            validate_invariants(state)

    def test_game_over_without_winner_fails(self):
        state = make_state(phase=Phase.GAME_OVER)
        with pytest.raises(AssertionError, match="winner is None"):
            validate_invariants(state)

    def test_game_over_with_winner_passes(self):
        from engine.game_state import WinReason
        state = make_state(phase=Phase.GAME_OVER, winner=PlayerID.P1,
                           win_reason=WinReason.LIFE_AND_LEADER_HIT)
        validate_invariants(state)

    def test_game_over_without_win_reason_fails(self):
        from engine.game_state import WinReason
        state = make_state(phase=Phase.GAME_OVER, winner=PlayerID.P1, win_reason=None)
        with pytest.raises(AssertionError, match="win_reason is None"):
            validate_invariants(state)

    def test_game_over_with_win_reason_passes(self):
        from engine.game_state import WinReason
        state = make_state(phase=Phase.GAME_OVER, winner=PlayerID.P1,
                           win_reason=WinReason.LIFE_AND_LEADER_HIT)
        validate_invariants(state)

    def test_battle_context_required_in_battle_phase(self):
        """battle_context=None while in a battle phase is invalid."""
        state = make_state(phase=Phase.BATTLE_BLOCKER, battle_context=None)
        with pytest.raises(AssertionError, match="battle_context is None"):
            validate_invariants(state)

    def test_battle_context_absent_outside_battle(self):
        """battle_context set while not in a battle phase is invalid."""
        ctx = BattleContext(attacker_id="p1-0", target_id="p2-leader")
        state = make_state(phase=Phase.MAIN, battle_context=ctx)
        with pytest.raises(AssertionError, match="battle_context is set"):
            validate_invariants(state)


# ── Phase machine ──────────────────────────────────────────────────────────────

class TestPhaseMachine:
    def test_automatic_phases(self):
        auto = {Phase.REFRESH, Phase.DRAW, Phase.DON, Phase.END,
                Phase.BATTLE_DECLARED, Phase.BATTLE_WHEN_ATK,
                Phase.BATTLE_DAMAGE, Phase.BATTLE_CLEANUP}
        for phase in auto:
            assert is_automatic(phase), f"{phase} should be automatic"

    def test_non_automatic_phases(self):
        non_auto = {Phase.SETUP, Phase.MAIN, Phase.BATTLE_BLOCKER,
                    Phase.BATTLE_COUNTER, Phase.BATTLE_TRIGGER}
        for phase in non_auto:
            assert not is_automatic(phase), f"{phase} should not be automatic"

    def test_legal_actions_in_main(self):
        state = make_state(phase=Phase.MAIN)
        assert is_legal_action(Phase.MAIN, PlayCard("p1-0"), False)
        assert is_legal_action(Phase.MAIN, EndTurn(), False)
        assert is_legal_action(Phase.MAIN, DeclareAttack("p1-0", "p2-leader"), False)
        assert not is_legal_action(Phase.MAIN, PassCounter(), False)
        assert not is_legal_action(Phase.MAIN, DeclareBlocker("p1-0"), False)

    def test_only_respond_input_when_waiting(self):
        """While pending_input is set, every action except RespondInput is illegal."""
        for action in [PlayCard("x"), EndTurn(), PassCounter(), DeclareBlocker("x")]:
            assert not is_legal_action(Phase.MAIN, action, has_pending_input=True)
        assert is_legal_action(Phase.MAIN, RespondInput(("yes",)), has_pending_input=True)

    def test_counter_window_actions(self):
        assert is_legal_action(Phase.BATTLE_COUNTER, PlayCounter("p2-3"), False)
        assert is_legal_action(Phase.BATTLE_COUNTER, PassCounter(), False)
        assert not is_legal_action(Phase.BATTLE_COUNTER, EndTurn(), False)

    def test_blocker_window_actions(self):
        assert is_legal_action(Phase.BATTLE_BLOCKER, DeclareBlocker("p2-3"), False)
        assert is_legal_action(Phase.BATTLE_BLOCKER, PassBlocker(), False)
        assert not is_legal_action(Phase.BATTLE_BLOCKER, PlayCounter("p2-3"), False)

    def test_trigger_window_actions(self):
        assert is_legal_action(Phase.BATTLE_TRIGGER, ActivateTrigger(), False)
        assert is_legal_action(Phase.BATTLE_TRIGGER, PassTrigger(), False)
        assert not is_legal_action(Phase.BATTLE_TRIGGER, EndTurn(), False)

    def test_no_actions_in_game_over(self):
        assert not is_legal_action(Phase.GAME_OVER, EndTurn(), False)
        assert not is_legal_action(Phase.GAME_OVER, RespondInput(()), True)


class TestPhaseOrder:
    def test_battle_cleanup_after_battle_counter(self):
        assert phase_has_passed(Phase.BATTLE_CLEANUP, Phase.BATTLE_COUNTER)

    def test_main_not_after_end(self):
        # MAIN comes before END in a turn
        assert not phase_has_passed(Phase.MAIN, Phase.END)

    def test_same_phase_is_not_passed(self):
        assert not phase_has_passed(Phase.MAIN, Phase.MAIN)

    def test_setup_not_in_order(self):
        # SETUP is not in PHASE_ORDER — returns False safely
        assert not phase_has_passed(Phase.SETUP, Phase.MAIN)

    def test_phase_order_completeness(self):
        """Every phase except SETUP and GAME_OVER should be in PHASE_ORDER."""
        excluded = {Phase.SETUP, Phase.GAME_OVER}
        for phase in Phase:
            if phase not in excluded:
                assert phase in PHASE_ORDER, f"{phase} missing from PHASE_ORDER"

    def test_defending_player_phases(self):
        dp = defending_player_phases()
        assert Phase.BATTLE_BLOCKER in dp
        assert Phase.BATTLE_COUNTER in dp
        assert Phase.BATTLE_TRIGGER in dp
        assert Phase.MAIN not in dp
        assert Phase.BATTLE_DAMAGE not in dp


class TestAdvancePhase:
    def test_advance_phase_action_exists(self):
        from engine.actions import AdvancePhase
        action = AdvancePhase()
        assert action is not None

    def test_advance_phase_legal_in_refresh(self):
        from engine.actions import AdvancePhase
        assert is_legal_action(Phase.REFRESH, AdvancePhase(), False)

    def test_advance_phase_legal_in_draw(self):
        from engine.actions import AdvancePhase
        assert is_legal_action(Phase.DRAW, AdvancePhase(), False)

    def test_advance_phase_legal_in_don(self):
        from engine.actions import AdvancePhase
        assert is_legal_action(Phase.DON, AdvancePhase(), False)

    def test_advance_phase_legal_in_end(self):
        from engine.actions import AdvancePhase
        assert is_legal_action(Phase.END, AdvancePhase(), False)

    def test_advance_phase_legal_in_battle_auto_phases(self):
        from engine.actions import AdvancePhase
        for phase in (Phase.BATTLE_DECLARED, Phase.BATTLE_WHEN_ATK,
                      Phase.BATTLE_DAMAGE, Phase.BATTLE_CLEANUP):
            assert is_legal_action(phase, AdvancePhase(), False), f"AdvancePhase should be legal in {phase}"

    def test_advance_phase_NOT_legal_in_main(self):
        from engine.actions import AdvancePhase
        assert not is_legal_action(Phase.MAIN, AdvancePhase(), False)

    def test_advance_phase_NOT_legal_in_battle_trigger(self):
        """BATTLE_TRIGGER is a defender decision phase (ActivateTrigger / PassTrigger)."""
        from engine.actions import AdvancePhase
        assert not is_legal_action(Phase.BATTLE_TRIGGER, AdvancePhase(), False)
