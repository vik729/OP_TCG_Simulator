import pytest
from engine.game_state import ScopedEffect


def test_scoped_effect_default_fields():
    se = ScopedEffect(target_instance_id="p1-leader",
                      modification={"type": "PowerMod", "amount": 1000})
    assert se.target_instance_id == "p1-leader"
    assert se.modification == {"type": "PowerMod", "amount": 1000}
    assert se.applies_when == "always"
    assert se.expires_at == "BATTLE_CLEANUP"
    assert se.expires_at_turn is None


def test_scoped_effect_is_frozen():
    se = ScopedEffect(target_instance_id="p1-leader",
                      modification={"type": "PowerMod", "amount": 1000})
    with pytest.raises(Exception):
        se.power_modifier = -1000  # type: ignore
