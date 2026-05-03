"""T13: CardDB picks up YAML triggers from cards/effects/<set>/<card_id>.yaml."""
import pathlib
import pytest


def test_card_db_loads_yaml_triggers_from_effects_dir():
    effects_path = pathlib.Path("cards/effects/ST01/ST01-007.yaml")
    backup = None
    if effects_path.exists():
        backup = effects_path.read_text(encoding="utf-8")
    effects_path.write_text("""\
card_id: ST01-007
dsl_status: parsed
authored_by: test

triggers:
  - "on": OnPlay
    effect: { type: Draw, count: 1 }
""", encoding="utf-8")
    try:
        from engine.card_db import CardDB
        db = CardDB()
        cdef = db.get("ST01-007")
        assert cdef is not None
        assert cdef.dsl_status == "parsed"
        assert len(cdef.triggers) == 1
        assert cdef.triggers[0]["on"] == "OnPlay"
        assert cdef.triggers[0]["effect"]["type"] == "Draw"
    finally:
        if backup is not None:
            effects_path.write_text(backup, encoding="utf-8")
        else:
            effects_path.unlink()


def test_card_db_dsl_status_vanilla_for_no_effect_text():
    """Cards with no effect_text default to dsl_status=vanilla."""
    from engine.card_db import CardDB
    db = CardDB()
    # ST01-008 Nico Robin has effect_text=None per inspection
    cdef = db.get("ST01-008")
    assert cdef.dsl_status == "vanilla"


def test_card_db_dsl_status_pending_for_unauthored_effect_text():
    """Cards with effect_text but no YAML default to dsl_status=pending."""
    from engine.card_db import CardDB
    db = CardDB()
    # ST01-002 Usopp has effect_text but no YAML authored yet
    cdef = db.get("ST01-002")
    assert cdef.dsl_status == "pending"
