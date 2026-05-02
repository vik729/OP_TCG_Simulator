"""Tests for engine/resolver.py - vanilla MVP stub."""
import pytest
import dataclasses
from engine.resolver import resolve_top
from engine.game_state import StackEntry, PlayerID
from tests.test_game_state import make_state


class TestResolverStub:
    def test_empty_stack_passes_through(self):
        """Empty effect stack -> resolve_top is a no-op."""
        state = make_state()
        assert state.effect_stack == ()
        result = resolve_top(state)
        assert result == state

    def test_non_empty_stack_raises(self):
        """Vanilla MVP: any non-empty stack means the DSL was wrongly invoked."""
        entry = StackEntry(
            effect={"type": "Draw", "n": 1},
            source_instance_id="p1-leader",
            controller=PlayerID.P1,
        )
        state = make_state(effect_stack=(entry,))
        with pytest.raises(NotImplementedError, match="Resolver not implemented"):
            resolve_top(state)
