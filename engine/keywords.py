"""
engine/keywords.py
==================
Central query for "does this card have keyword X right now?"

Three levels (per spec §7.4):
  L1 innate always-on:  CardDefinition.keywords
  L2 innate conditional: CardDefinition.conditional_keywords (vanilla: empty)
  L3 runtime grants:    state.scoped_effects KeywordGrant entries (added in DSL phase)

Engine code MUST go through effective_keywords() — never read keywords fields
directly. This is the abstraction boundary that lets DSL phase add L2/L3
without touching engine internals.
"""
from __future__ import annotations
from engine.game_state import CardInstance, GameState
from engine.card_db import CardDB


def evaluate_condition(condition: dict, card: CardInstance, state: GameState) -> bool:
    """Evaluate an L2 conditional keyword grant.

    Vanilla MVP supports only:
      {"type": "don_attached_min", "value": N}
        true if card.attached_don >= N

    All other condition types raise NotImplementedError. The DSL phase will
    extend this with more types ([Your Turn], [Opponent's Turn], etc.).
    """
    cond_type = condition.get("type")
    if cond_type == "don_attached_min":
        return card.attached_don >= condition["value"]
    raise NotImplementedError(
        f"Condition type {cond_type!r} not supported in vanilla MVP"
    )


def effective_keywords(card: CardInstance, db: CardDB,
                       state: GameState) -> frozenset[str]:
    """Return the set of keywords this card effectively has right now.

    Unions L1 (innate), L2 (conditional whose conditions are met),
    and L3 (temp grants on the instance).
    """
    definition = db.get(card.definition_id)
    result: set[str] = set(definition.keywords)
    for grant in definition.conditional_keywords:
        if evaluate_condition(grant.condition, card, state):
            result.add(grant.keyword)
    from engine.dsl.lookups import granted_keywords
    result |= granted_keywords(state, card.instance_id)
    return frozenset(result)
