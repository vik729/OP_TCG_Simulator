"""
engine/replay.py
================
JSONL trace recording, save, and load.

A trace is a list of dicts. The first dict is a header (type=header) carrying
seed, decklists, and ruleset_id - enough to reconstruct the initial state.
Subsequent dicts are action records (type=action). The final dict is a result
record (type=result) once the game ends.

Engine code itself never touches replay - play.py records as actions are dispatched.
This keeps step() pure.
"""
from __future__ import annotations
import json
import dataclasses
from pathlib import Path
from typing import Any
from engine.actions import (
    Action,
    ChooseFirst, AdvancePhase, RespondInput,
    PlayCard, ActivateAbility, AttachDon, DeclareAttack, EndTurn,
    DeclareBlocker, PassBlocker,
    PlayCounter, PassCounter,
    ActivateTrigger, PassTrigger,
)
from engine.game_state import Phase, PlayerID


# Map _type string -> Action class for deserialization
_ACTION_TYPES: dict[str, type[Action]] = {
    "ChooseFirst": ChooseFirst,
    "AdvancePhase": AdvancePhase,
    "RespondInput": RespondInput,
    "PlayCard": PlayCard,
    "ActivateAbility": ActivateAbility,
    "AttachDon": AttachDon,
    "DeclareAttack": DeclareAttack,
    "EndTurn": EndTurn,
    "DeclareBlocker": DeclareBlocker,
    "PassBlocker": PassBlocker,
    "PlayCounter": PlayCounter,
    "PassCounter": PassCounter,
    "ActivateTrigger": ActivateTrigger,
    "PassTrigger": PassTrigger,
}


def serialize_action(action: Action) -> dict[str, Any]:
    """Convert an Action dataclass into a JSON-safe dict."""
    out: dict[str, Any] = {"_type": type(action).__name__}
    if dataclasses.is_dataclass(action):
        for f in dataclasses.fields(action):
            value = getattr(action, f.name)
            if isinstance(value, tuple):
                value = list(value)
            out[f.name] = value
    return out


def deserialize_action(data: dict[str, Any]) -> Action:
    """Convert a JSON dict back into an Action dataclass."""
    type_name = data["_type"]
    cls = _ACTION_TYPES[type_name]
    kwargs: dict[str, Any] = {}
    for f in dataclasses.fields(cls):
        if f.name in data:
            value = data[f.name]
            if "tuple" in str(f.type):
                value = tuple(value)
            kwargs[f.name] = value
    return cls(**kwargs)


def record_action(trace: list[dict], action: Action, turn: int,
                  phase: Phase, actor: PlayerID) -> None:
    """Append an action record to the trace."""
    trace.append({
        "type": "action",
        "turn": turn,
        "phase": phase.value,
        "actor": actor.value,
        "action": serialize_action(action),
    })


def record_result(trace: list[dict], winner: PlayerID, win_reason: str,
                  turns: int) -> None:
    """Append a result record to the trace (called on GAME_OVER)."""
    trace.append({
        "type": "result",
        "winner": winner.value,
        "win_reason": win_reason,
        "turns": turns,
    })


def save_trace(trace: list[dict], path: Path, header_meta: dict) -> None:
    """Write trace to JSONL file. Header is prepended automatically."""
    header = {"type": "header", **header_meta}
    lines = [json.dumps(header)]
    lines.extend(json.dumps(record) for record in trace)
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def load_trace(path: Path) -> list[dict]:
    """Load a JSONL trace file. Returns the full record list including header."""
    content = Path(path).read_text(encoding="utf-8")
    return [json.loads(line) for line in content.strip().split("\n") if line]


def replay_actions(trace: list[dict]) -> list[Action]:
    """Extract just the Actions from a trace, in order. Useful for replay()."""
    return [deserialize_action(r["action"]) for r in trace if r["type"] == "action"]
