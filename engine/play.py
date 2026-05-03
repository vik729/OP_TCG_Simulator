"""
engine/play.py
==============
CLI entry point.

Usage:
    python -m engine.play --p1 ST-01 --p2 ST-02 --seed 42 [--bot-seed 7]
                          [--log path.jsonl] [--verbose]
    python -m engine.play --replay path.jsonl [--until-turn N] [--verbose]
"""
from __future__ import annotations
import argparse
import random
import sys
from pathlib import Path
from datetime import datetime, timezone
from engine.card_db import CardDB
from engine.deck import load_official_deck
from engine.ruleset import RULESETS
from engine.setup import build_initial_state
from engine.step import step
from engine.bots.random_bot import random_legal_action
from engine.replay import (
    record_action, record_result, save_trace, load_trace,
    deserialize_action,
)
from engine.game_state import Phase, PlayerID, GameState
from engine.card_db import CardDB
from engine.actions import (
    Action, AdvancePhase, PlayCard, AttachDon, DeclareAttack, DeclareBlocker,
    PassBlocker, PlayCounter, PassCounter, ActivateAbility, ActivateTrigger,
    PassTrigger, RespondInput, ChooseFirst,
)
from engine.combat import battle_power


def _card_label(state: GameState, db: CardDB, instance_id: str) -> str:
    """'ST01-006 "Usopp"' if findable, else the bare instance_id."""
    card = state.get_card(instance_id)
    if card is None:
        return instance_id
    cdef = db.get(card.definition_id)
    name = (cdef.name if cdef and cdef.name else "?").strip()
    return f'{card.definition_id} "{name}"'


def _action_actor(state: GameState, action: Action) -> PlayerID:
    """During blocker/counter/trigger windows, the *defender* acts."""
    defender_actions = (DeclareBlocker, PassBlocker, PlayCounter, PassCounter,
                        ActivateTrigger, PassTrigger)
    if isinstance(action, defender_actions):
        return state.active_player_id.opponent()
    return state.active_player_id


def _format_action(action: Action, state: GameState, db: CardDB) -> str:
    name = type(action).__name__
    if isinstance(action, PlayCard):
        card = state.get_card(action.card_instance_id)
        cdef = db.get(card.definition_id) if card else None
        cost = (cdef.cost or 0) if cdef else 0
        extra = f" +{action.extra_don}don" if action.extra_don else ""
        return (f"PlayCard {_card_label(state, db, action.card_instance_id)} "
                f"(cost {cost}){extra}")
    if isinstance(action, AttachDon):
        return f"AttachDon -> {_card_label(state, db, action.target_instance_id)}"
    if isinstance(action, DeclareAttack):
        return (f"DeclareAttack {_card_label(state, db, action.attacker_instance_id)} "
                f"-> {_card_label(state, db, action.target_instance_id)}")
    if isinstance(action, DeclareBlocker):
        return f"DeclareBlocker {_card_label(state, db, action.blocker_instance_id)}"
    if isinstance(action, PlayCounter):
        card = state.get_card(action.card_instance_id)
        cdef = db.get(card.definition_id) if card else None
        boost = (cdef.counter or 0) if cdef else 0
        return f"PlayCounter {_card_label(state, db, action.card_instance_id)} (+{boost})"
    if isinstance(action, ActivateAbility):
        return f"ActivateAbility {_card_label(state, db, action.card_instance_id)}"
    if isinstance(action, RespondInput):
        return f"RespondInput {action.choices}"
    if isinstance(action, ChooseFirst):
        return f"ChooseFirst {action.first_player_id}"
    return name


def _phase_delta(prev: GameState, cur: GameState, db: CardDB) -> str | None:
    """One-line summary of what an auto-phase did. None if not interesting."""
    actor = prev.active_player_id
    pp, pc = prev.get_player(actor), cur.get_player(actor)

    if prev.phase == Phase.REFRESH:
        don_returned = (pp.leader.attached_don
                        + sum(c.attached_don for c in pp.field))
        don_unrest_cost = pp.don_field.rested
        char_unrest = sum(1 for c in pp.field if c.rested)
        leader_unrest = 1 if pp.leader.rested else 0
        parts = []
        if leader_unrest:
            parts.append("leader")
        if char_unrest > 0:
            parts.append(f"{char_unrest} char")
        if don_returned > 0:
            parts.append(f"{don_returned} don returned from board")
        if don_unrest_cost > 0:
            parts.append(f"{don_unrest_cost} don unrested in cost area")
        return f"refreshed {', '.join(parts)}" if parts else "nothing to refresh"

    if prev.phase == Phase.DRAW:
        drew = len(pc.hand) - len(pp.hand)
        if drew <= 0:
            return "no draw (first turn)"
        prev_ids = {c.instance_id for c in pp.hand}
        new_cards = [c for c in pc.hand if c.instance_id not in prev_ids]
        names = ", ".join(_card_label(cur, db, c.instance_id) for c in new_cards)
        return f"drew {drew}: {names}"

    if prev.phase == Phase.DON:
        added = pc.don_field.total - pp.don_field.total
        return (f"added {added} DON "
                f"(now {pc.don_field.active}a/{pc.don_field.rested}r)")

    if prev.phase == Phase.BATTLE_DAMAGE:
        return _battle_damage_delta(prev, cur, db)

    return None


def _battle_damage_delta(pre: GameState, cur: GameState, db: CardDB) -> str | None:
    """Describe the outcome of a battle: MISS, KO, leader hit, or GAME OVER."""
    bc = pre.battle_context
    if bc is None:
        return None
    attacker = pre.get_card(bc.attacker_id)
    target = pre.get_card(bc.target_id)
    if attacker is None or target is None:
        return None

    a_def = db.get(attacker.definition_id)
    t_def = db.get(target.definition_id)
    a_power = battle_power(attacker, a_def, pre)
    t_power = battle_power(target, t_def, pre) + sum(bc.power_boosts)
    for se in pre.scoped_effects:
        if se.modification.get("type") != "PowerMod":
            continue
        amount = se.modification.get("amount", 0)
        if se.target_instance_id == attacker.instance_id:
            a_power += amount
        if se.target_instance_id == target.instance_id:
            t_power += amount

    power_str = f"{a_power} vs {t_power}"

    if cur.phase == Phase.GAME_OVER:
        return f"HIT leader -> GAME OVER ({power_str})"
    if a_power < t_power:
        return f"MISS ({power_str})"
    if t_def.type == "Leader":
        pre_p = pre.get_player(target.controller)
        cur_p = cur.get_player(target.controller)
        damage = len(pre_p.life) - len(cur_p.life)
        moved = pre_p.life[:damage]
        moved_ids = {c.instance_id for c in moved}
        cur_hand_ids = {c.instance_id for c in cur_p.hand}
        dest = "hand" if moved_ids and moved_ids.issubset(cur_hand_ids) else "trash"
        names = ", ".join(_card_label(cur, db, c.instance_id) for c in moved) or "?"
        suffix = " (Double Attack)" if damage > 1 else ""
        return (f"HIT leader, {damage} life damage{suffix}"
                f" -> {target.controller.value} life-to-{dest}: {names} ({power_str})")
    return f"KO'd {_card_label(pre, db, target.instance_id)} ({power_str})"


def _player_summary(p) -> str:
    att = p.leader.attached_don + sum(c.attached_don for c in p.field)
    att_str = f" att={att}" if att else ""
    return (f"life={len(p.life)} hand={len(p.hand)} field={len(p.field)} "
            f"don={p.don_field.active}a/{p.don_field.rested}r{att_str}")


def _turn_header(state: GameState) -> str:
    return (
        f"=== Turn {state.turn_number} ({state.active_player_id.value}) "
        f"| P1: {_player_summary(state.p1)} "
        f"|| P2: {_player_summary(state.p2)} ==="
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="OP TCG simulator CLI")
    parser.add_argument("--p1", help="P1 deck id (e.g. ST-01)")
    parser.add_argument("--p2", help="P2 deck id (e.g. ST-02)")
    parser.add_argument("--seed", type=int, default=42, help="Game RNG seed")
    parser.add_argument("--bot-seed", type=int, default=None, help="Bot RNG seed (default: seed+100k)")
    parser.add_argument("--log", help="Path to write JSONL trace")
    parser.add_argument("--replay", help="Path to a JSONL trace to replay")
    parser.add_argument("--until-turn", type=int, default=None, help="Stop replay at turn N")
    parser.add_argument("--verbose", action="store_true", help="Print every action")
    args = parser.parse_args(argv)

    db = CardDB()
    ruleset = RULESETS["ST01-ST04-v1"]

    if args.replay:
        return _do_replay(args, db, ruleset)

    if not args.p1 or not args.p2:
        parser.error("--p1 and --p2 are required when not using --replay")

    bot_seed = args.bot_seed if args.bot_seed is not None else args.seed + 100_000

    p1_deck = load_official_deck(args.p1, db)
    p2_deck = load_official_deck(args.p2, db)
    state = build_initial_state(p1_deck, p2_deck, seed=args.seed, ruleset=ruleset, db=db)
    bot_rng = random.Random(bot_seed)

    trace: list[dict] = []
    prev_turn = -1
    while not state.is_terminal():
        if args.verbose and state.turn_number != prev_turn:
            print(_turn_header(state))
            prev_turn = state.turn_number
        action = random_legal_action(state, bot_rng, db)
        actor = _action_actor(state, action)
        pre = state
        record_action(trace, action, turn=state.turn_number, phase=state.phase, actor=actor)
        state = step(state, action, db)
        if args.verbose:
            line = f"  [{pre.phase.value}] {actor.value}: {_format_action(action, pre, db)}"
            if isinstance(action, AdvancePhase):
                delta = _phase_delta(pre, state, db)
                if delta:
                    line += f"  -> {delta}"
            print(line)
        if state.turn_number >= 500:
            print(f"Aborted at turn {state.turn_number} (500-turn cap)", file=sys.stderr)
            return 1

    record_result(trace, state.winner, state.win_reason.value, state.turn_number)

    if args.log:
        header = {
            "schema": 1,
            "seed": args.seed,
            "bot_seed": bot_seed,
            "p1_deck": args.p1,
            "p2_deck": args.p2,
            "ruleset_id": ruleset.id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        save_trace(trace, Path(args.log), header_meta=header)

    print(f"Winner: {state.winner.value} ({state.win_reason.value}) - {state.turn_number} turns")
    return 0


def _do_replay(args, db, ruleset) -> int:
    trace = load_trace(Path(args.replay))
    header = trace[0]
    actions = [deserialize_action(r["action"]) for r in trace if r["type"] == "action"]

    p1_deck = load_official_deck(header["p1_deck"], db)
    p2_deck = load_official_deck(header["p2_deck"], db)
    state = build_initial_state(p1_deck, p2_deck, seed=header["seed"], ruleset=ruleset, db=db)

    for action in actions:
        if args.until_turn is not None and state.turn_number >= args.until_turn:
            break
        if args.verbose:
            print(f"[turn {state.turn_number} phase {state.phase.value}]: {type(action).__name__}")
        state = step(state, action, db)

    if state.is_terminal():
        print(f"Replay end: Winner {state.winner.value} ({state.win_reason.value}) at turn {state.turn_number}")
    else:
        print(f"Replay paused at turn {state.turn_number}, phase {state.phase.value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
