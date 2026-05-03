"""Operators usable inside the `cost` array of an ActivateMain trigger.

Each cost operator returns the new state on success or raises
ActivationCostFailed on failure. Costs are paid atomically — if ANY cost
fails, the activation is aborted with no state change.
"""
from __future__ import annotations
import dataclasses
from engine.game_state import GameState, PlayerID, DonField


class ActivationCostFailed(Exception):
    pass


def apply_cost(node: dict, state: GameState, *,
                source_controller: PlayerID, source_id: str) -> GameState:
    t = node.get("type")
    if t == "RestSelf":
        return _rest_self(state, source_id)
    if t == "RestDon":
        return _rest_don(state, source_controller, node.get("amount", 1))
    raise ActivationCostFailed(f"Unknown cost operator {t!r}")


def _rest_self(state: GameState, source_id: str) -> GameState:
    card = state.get_card(source_id)
    if card is None:
        raise ActivationCostFailed(f"RestSelf: source {source_id} not found")
    if card.rested:
        raise ActivationCostFailed(f"RestSelf: source {source_id} already rested")
    new_card = dataclasses.replace(card, rested=True)
    return _replace_card(state, source_id, new_card)


def _rest_don(state: GameState, controller: PlayerID, amount: int) -> GameState:
    player = state.get_player(controller)
    if player.don_field.active < amount:
        raise ActivationCostFailed(
            f"RestDon: need {amount} active, have {player.don_field.active}")
    new_don = DonField(
        active=player.don_field.active - amount,
        rested=player.don_field.rested + amount,
    )
    new_player = dataclasses.replace(player, don_field=new_don)
    if controller == PlayerID.P1:
        return dataclasses.replace(state, p1=new_player)
    return dataclasses.replace(state, p2=new_player)


def _replace_card(state, instance_id, new_card):
    for pid in (PlayerID.P1, PlayerID.P2):
        player = state.get_player(pid)
        if player.leader.instance_id == instance_id:
            new_player = dataclasses.replace(player, leader=new_card)
            return (dataclasses.replace(state, p1=new_player) if pid == PlayerID.P1
                    else dataclasses.replace(state, p2=new_player))
        for zone_name in ("hand", "deck", "field", "life", "trash"):
            zone = getattr(player, zone_name)
            for i, c in enumerate(zone):
                if c.instance_id == instance_id:
                    new_zone = zone[:i] + (new_card,) + zone[i+1:]
                    new_player = dataclasses.replace(player, **{zone_name: new_zone})
                    return (dataclasses.replace(state, p1=new_player) if pid == PlayerID.P1
                            else dataclasses.replace(state, p2=new_player))
    return state
