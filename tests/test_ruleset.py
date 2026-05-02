"""Tests for engine/ruleset.py."""
import pytest
from engine.ruleset import Ruleset, RULESETS


class TestRuleset:
    def test_construct_empty_banlist(self):
        rs = Ruleset(id="test")
        assert rs.banlist == frozenset()

    def test_construct_with_banlist(self):
        rs = Ruleset(id="test", banlist=frozenset({"OP01-001"}))
        assert "OP01-001" in rs.banlist

    def test_frozen(self):
        rs = Ruleset(id="test")
        with pytest.raises((AttributeError, TypeError)):
            rs.id = "other"  # type: ignore


class TestRulesetsRegistry:
    def test_default_ruleset_present(self):
        assert "ST01-ST04-v1" in RULESETS

    def test_default_ruleset_empty_banlist(self):
        assert RULESETS["ST01-ST04-v1"].banlist == frozenset()
