"""Filter evaluator. A filter is a dict that selects matching CardInstances."""
from __future__ import annotations
from typing import Optional
from engine.game_state import GameState, CardInstance, PlayerID, Zone
from engine.card_db import CardDB


def matches(card: CardInstance, filter_dict: dict, state: GameState,
            *, source_controller: PlayerID, db: CardDB,
            source_id: Optional[str] = None) -> bool:
    """Does `card` satisfy the filter dict?

    Required context: source_controller (the controller of the effect's source
    card, used to resolve "own" vs "opponent"), and source_id for `this_card`
    self-references.
    """
    cdef = db.get(card.definition_id)
    if cdef is None:
        return False

    ctrl = filter_dict.get("controller", "own")
    if ctrl == "own" and card.controller != source_controller:
        return False
    if ctrl == "opponent" and card.controller == source_controller:
        return False

    expected_zone = filter_dict.get("zone", "field")
    zone_map = {"field": Zone.FIELD, "hand": Zone.HAND,
                "leader": Zone.FIELD, "character": Zone.FIELD}
    target_zone = zone_map.get(expected_zone, Zone.FIELD)
    if expected_zone == "leader" and cdef.type != "Leader":
        return False
    if expected_zone == "character" and cdef.type != "Character":
        return False
    if card.zone != target_zone:
        return False

    if "type" in filter_dict:
        wanted = filter_dict["type"]
        if isinstance(wanted, list):
            if cdef.type not in wanted:
                return False
        elif cdef.type != wanted:
            return False

    if "subtype_includes" in filter_dict:
        card_subtypes = set(cdef.subtypes or [])
        for required in filter_dict["subtype_includes"]:
            if required not in card_subtypes:
                return False

    if "color_includes" in filter_dict:
        card_colors = set(cdef.color or [])
        wanted_colors = set(filter_dict["color_includes"])
        if not (card_colors & wanted_colors):
            return False

    base_power = cdef.power or 0
    if "power_le" in filter_dict and base_power > filter_dict["power_le"]:
        return False
    if "power_ge" in filter_dict and base_power < filter_dict["power_ge"]:
        return False

    if "cost_le" in filter_dict and (cdef.cost or 0) > filter_dict["cost_le"]:
        return False

    if "rested" in filter_dict and card.rested != filter_dict["rested"]:
        return False

    if filter_dict.get("this_card"):
        if source_id is None or card.instance_id != source_id:
            return False

    if filter_dict.get("not_this_card"):
        if source_id is not None and card.instance_id == source_id:
            return False

    return True


def find_targets(filter_dict: dict, state: GameState, *,
                 source_controller: PlayerID, db: CardDB,
                 source_id: Optional[str] = None) -> list[CardInstance]:
    """Return all CardInstances in the game that satisfy the filter."""
    expected_zone = filter_dict.get("zone", "field")

    candidates: list[CardInstance] = []
    for player in (state.p1, state.p2):
        if expected_zone in ("field", "leader", "character"):
            candidates.append(player.leader)
            candidates.extend(player.field)
        elif expected_zone == "hand":
            candidates.extend(player.hand)

    return [c for c in candidates
            if matches(c, filter_dict, state,
                       source_controller=source_controller, db=db,
                       source_id=source_id)]
