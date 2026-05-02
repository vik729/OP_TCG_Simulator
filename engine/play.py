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
from engine.game_state import Phase, PlayerID


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
    while not state.is_terminal():
        action = random_legal_action(state, bot_rng, db)
        actor = state.active_player_id
        if args.verbose:
            print(f"[turn {state.turn_number} phase {state.phase.value}] {actor.value}: {type(action).__name__}")
        record_action(trace, action, turn=state.turn_number, phase=state.phase, actor=actor)
        state = step(state, action, db)
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
