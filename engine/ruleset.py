"""
engine/ruleset.py
=================
Ruleset = id + banlist. Errata overlay deferred.

The Ruleset is a first-class object passed into deck validation and game setup.
The id field is what gets stored on GameState.ruleset_id; the rest of the
engine never references the Ruleset directly during play.
"""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Ruleset:
    id: str
    banlist: frozenset[str] = field(default_factory=frozenset)


# Default registry - vanilla MVP has one ruleset.
RULESETS: dict[str, Ruleset] = {
    "ST01-ST04-v1": Ruleset(id="ST01-ST04-v1", banlist=frozenset()),
}
