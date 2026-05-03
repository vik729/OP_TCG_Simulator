"""Helpers for phase-scheduled and life-card trigger discovery and queuing."""
from __future__ import annotations
from engine.game_state import GameState, CardInstance, PlayerID
from engine.card_db import CardDB


def find_triggers_for_event(state: GameState, event_type: str,
                             controller: PlayerID, db: CardDB
                             ) -> list[tuple[CardInstance, dict]]:
    """Scan field (leader + characters) for cards owned by `controller`
    whose YAML triggers include event_type. Returns ordered list (by field
    position; leader first) of (card, trigger_dict) pairs."""
    player = state.get_player(controller)
    found: list[tuple[CardInstance, dict]] = []
    for card in (player.leader,) + player.field:
        cdef = db.get(card.definition_id)
        for trigger in (cdef.triggers or ()):
            if trigger.get("on") == event_type:
                found.append((card, trigger))
    return found
