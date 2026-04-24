# OP TCG Simulator

> Unofficial fan project. Not affiliated with or endorsed by Bandai.

An open-source, rules-complete simulator for the **One Piece Trading Card Game (OPTCG)** built for:
- Programmatic game play (no UI required)
- Reinforcement learning agent training
- Online human vs. human / human vs. bot play

---

## Architecture Overview

Four cleanly separated layers. Each can be developed, tested, and deployed independently.

```
Frontend (React + WebSocket)
        │
Game Server (FastAPI)
        │
Rules Engine (Pure Python) ◄── THIS is the current focus
        │
RL Environment Wrapper (Gymnasium / PettingZoo)
```

**Core design principle**: The Rules Engine is a pure state-transition function — `step(GameState, Action) → GameState`. No global state, no side effects. Card behavior is expressed entirely as JSON data (a DSL), never as per-card Python code.

→ Full design detail: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)

---

## Repository Structure

```
OP_TCG_Simulator/
├── cards/              # Card definitions (JSON, no code) — Phase 1 data layer
│   ├── ST01/           # Starter Deck 1: Straw Hat Crew
│   ├── ST02/           # Starter Deck 2: Worst Generation
│   ├── ST03/           # Starter Deck 3: Seven Warlords of the Sea
│   └── ST04/           # Starter Deck 4: Animal Kingdom Pirates
├── tools/              # Data pipeline scripts (not part of the engine)
│   ├── fetch_cards.py      # Phase 1: pulls raw card data from optcgapi.com
│   └── normalize_cards.py  # Phase 2: normalizes raw data to base card schema
├── docs/
│   ├── ARCHITECTURE.md     # Full design doc — read this before contributing
│   └── todos/
│       └── DSL_PIPELINE.md # Deferred: effect_text → DSL triggers[] pipeline
└── engine/             # (planned) Core rules engine — not started yet
```

> `cards/raw/` is gitignored — re-fetch at any time with `python tools/fetch_cards.py`.

---

## Build Roadmap

### Phase 1 — Engine (current focus)

| Step | Task | Status |
|------|------|--------|
| 1a | Card data pipeline: fetch raw data from OPTCG API | ✅ Done |
| 1b | Card data pipeline: normalize to base card schema | ✅ Done |
| 1c | Audit `effect_text` patterns across ST01–ST04 | 🔲 Next |
| 1d | Effect DSL schema design (informed by audit) | 🔲 Next |
| 1e | `GameState` and zone management | 🔲 Blocked on DSL schema |
| 1f | Turn structure and phase loop | 🔲 |
| 1g | Action enumeration (`legal_actions`) | 🔲 |
| 1h | Effect DSL interpreter | 🔲 |
| 1i | Combat resolution | 🔲 |
| 1j | Effect stack and trigger ordering | 🔲 |
| 1k | Win condition checking | 🔲 |
| 1l | Ruleset loading and errata overlay | 🔲 |
| 1m | Deck validation | 🔲 |

**Phase 1 milestone**: Two random bots play a complete, legal game end-to-end via CLI.

### Phase 2 — RL Environment
Gymnasium + PettingZoo wrapper, observation encoding, action masking, self-play training.
*Not started. Blocked on Phase 1.*

### Phase 3 — Web Product
React frontend, FastAPI WebSocket server, matchmaking, deck builder, accounts.
*Not started. Blocked on Phase 2.*

---

## Data Pipeline (how cards get into the system)

Card data is sourced from [optcgapi.com](https://www.optcgapi.com/documentation) — a free, open community API.

### Running the pipeline

```bash
# Step 1 — Fetch raw data (writes to cards/raw/, which is gitignored)
python tools/fetch_cards.py

# Step 2 — Normalize to base card schema (writes to cards/ST01/, ST02/, etc.)
python tools/normalize_cards.py
```

### Base card schema (what lives in `cards/STxx/*.json`)

```json
{
  "id": "ST01-001",
  "name": "Monkey D. Luffy",
  "type": "Leader",
  "color": ["Red"],
  "cost": null,
  "power": 5000,
  "counter": null,
  "life": 5,
  "attribute": "Strike",
  "subtypes": ["Straw Hat Crew"],
  "rarity": "L",
  "set_id": "ST01",
  "image_id": "ST01-001",
  "effect_text": "[DON!! x1] [When Attacking] Give up to 1 of your Leader or Character cards ...",
  "keywords": [],
  "triggers": [],
  "dsl_status": "pending"
}
```

`triggers` and `dsl_status` are filled in by the DSL pipeline (Phase 1d, deferred).
See [`docs/todos/DSL_PIPELINE.md`](docs/todos/DSL_PIPELINE.md) for the plan.

---

## Design Invariants

These must never be violated regardless of future changes:

1. `step(state, action) → state` is a pure function. No mutation, no global state.
2. Given the same `(initial_state, seed, action_sequence)`, the game always produces the same result.
3. Card definitions are data. No per-card Python code.
4. The engine has no knowledge of UI, networking, or RL.
5. A new card set is a data task, not an engineering task.
6. A rules change is a new ruleset file, not a code change.
7. Old games are always replayable under the ruleset they were played with.

---

## Legal

- License: Apache 2.0
- Card mechanics/rules: not copyrightable — safe to implement
- Card names, text, artwork: Bandai IP — never stored in this repo
- Card images: fetched at runtime from CDN, never committed
- Non-commercial fan project
