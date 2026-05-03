import pathlib
import pytest
from engine.dsl.loader import load_card_yaml, LoaderError, ALLOWED_DSL_STATUS


def _write(tmp_path, name, content):
    p = pathlib.Path(tmp_path) / name
    p.write_text(content, encoding="utf-8")
    return p


def test_load_simple_on_play_draw(tmp_path):
    yaml_str = """\
card_id: ST01-007
dsl_status: parsed
authored_by: human

triggers:
  - on: OnPlay
    effect:
      type: Draw
      count: 2
"""
    f = _write(tmp_path, "ST01-007.yaml", yaml_str)
    result = load_card_yaml(f)
    assert result["card_id"] == "ST01-007"
    assert result["dsl_status"] == "parsed"
    assert len(result["triggers"]) == 1
    assert result["triggers"][0]["on"] == "OnPlay"
    assert result["triggers"][0]["effect"] == {"type": "Draw", "count": 2}


def test_load_vanilla_card_with_no_triggers(tmp_path):
    yaml_str = """\
card_id: ST01-006
dsl_status: vanilla
authored_by: human
"""
    f = _write(tmp_path, "ST01-006.yaml", yaml_str)
    result = load_card_yaml(f)
    assert result["dsl_status"] == "vanilla"
    assert result["triggers"] == []


def test_loader_rejects_unknown_dsl_status(tmp_path):
    yaml_str = """\
card_id: ST01-007
dsl_status: bogus
"""
    f = _write(tmp_path, "ST01-007.yaml", yaml_str)
    with pytest.raises(LoaderError, match="dsl_status"):
        load_card_yaml(f)


def test_loader_rejects_missing_card_id(tmp_path):
    yaml_str = """\
dsl_status: vanilla
"""
    f = _write(tmp_path, "x.yaml", yaml_str)
    with pytest.raises(LoaderError, match="card_id"):
        load_card_yaml(f)


def test_loader_rejects_unknown_until_value(tmp_path):
    yaml_str = """\
card_id: ST01-005
dsl_status: parsed
authored_by: human
triggers:
  - on: WhenAttacking
    effect:
      type: GivePower
      target: { this_card: true }
      amount: 1000
      until: forever_and_ever
"""
    f = _write(tmp_path, "ST01-005.yaml", yaml_str)
    with pytest.raises(LoaderError, match="until"):
        load_card_yaml(f)


def test_loader_rejects_unknown_trigger(tmp_path):
    yaml_str = """\
card_id: ST01-005
dsl_status: parsed
triggers:
  - on: WhenSneezing
    effect: { type: Draw, count: 1 }
"""
    f = _write(tmp_path, "x.yaml", yaml_str)
    with pytest.raises(LoaderError, match="WhenSneezing"):
        load_card_yaml(f)
