"""YAML loader for card effect definitions.

Schema (per docs/superpowers/specs/2026-05-02-dsl-design.md §7.2):

    card_id:     str (required)
    dsl_status:  vanilla | parsed | manual_review (required)
    authored_by: str (optional, audit trail)
    triggers:    [ {on: str, effect: dict} ]   (optional; defaults to [])
"""
from __future__ import annotations
import pathlib
import yaml


ALLOWED_DSL_STATUS = {"vanilla", "parsed", "manual_review"}
ALLOWED_TRIGGERS = {"OnPlay", "WhenAttacking", "WhenBlocking", "OnKO",
                    "Counter", "ActivateMain", "EndOfYourTurn",
                    "AtStartOfYourTurn"}
ALLOWED_UNTIL = {"end_of_battle", "end_of_this_turn",
                 "end_of_opponent_turn", "end_of_your_next_turn"}


class LoaderError(ValueError):
    pass


def load_card_yaml(path) -> dict:
    """Load a card YAML file. Returns dict with card_id/dsl_status/triggers/...
    Raises LoaderError on schema violations."""
    p = pathlib.Path(path)
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    if raw is None:
        raise LoaderError(f"{p}: empty YAML")
    if "card_id" not in raw:
        raise LoaderError(f"{p}: missing required field card_id")
    status = raw.get("dsl_status")
    if status not in ALLOWED_DSL_STATUS:
        raise LoaderError(f"{p}: dsl_status {status!r} not in {ALLOWED_DSL_STATUS}")
    triggers = raw.get("triggers") or []
    normalized_triggers = []
    for i, t in enumerate(triggers):
        # YAML 1.1 converts unquoted `on:` to bool True; tolerate both.
        on = t.get("on", t.get(True))
        if on not in ALLOWED_TRIGGERS:
            raise LoaderError(f"{p}: trigger[{i}].on {on!r} not in {ALLOWED_TRIGGERS}")
        effect = t.get("effect")
        if not isinstance(effect, dict):
            raise LoaderError(f"{p}: trigger[{i}].effect must be a dict")
        _validate_effect_tree(effect, location=f"{p}: trigger[{i}].effect")
        normalized_triggers.append({"on": on, "effect": effect})
    return {
        "card_id":     raw["card_id"],
        "dsl_status":  status,
        "authored_by": raw.get("authored_by"),
        "triggers":    normalized_triggers,
    }


def _validate_effect_tree(node: dict, location: str) -> None:
    until = node.get("until")
    if until is not None and until not in ALLOWED_UNTIL:
        raise LoaderError(f"{location}: until {until!r} not in {ALLOWED_UNTIL}")
    t = node.get("type")
    if t == "Sequence":
        for i, step in enumerate(node.get("steps", [])):
            _validate_effect_tree(step, f"{location}.steps[{i}]")
    elif t == "If":
        if "then" in node:
            _validate_effect_tree(node["then"], f"{location}.then")
        if "else" in node:
            _validate_effect_tree(node["else"], f"{location}.else")
    elif t == "Choice":
        if "effect" in node:
            _validate_effect_tree(node["effect"], f"{location}.effect")
    elif t == "ForEach":
        if "do" in node:
            _validate_effect_tree(node["do"], f"{location}.do")
