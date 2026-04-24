# OP TCG Simulator — Architecture & Design Knowledge Base

> Living document. Updated as decisions are made and understanding deepens.
> Last updated: 2026-04

---

## Project Goal

Build a faithful, rules-complete simulator for the One Piece Trading Card Game (OPTCG) that:
- Runs games end-to-end programmatically (no UI required)
- Supports a reinforcement learning environment wrapper
- Can be hosted online for human play
- Is open-source and extensible

---

## High-Level Architecture

Four cleanly separated layers. Each can be developed, tested, and deployed independently.

```
┌─────────────────────────────────────────────────────┐
│                    Frontend (Web UI)                │
│          React + WebSocket — renders state          │
└─────────────────────┬───────────────────────────────┘
                      │ WebSocket / HTTP
┌─────────────────────▼───────────────────────────────┐
│                   Game Server                       │
│     FastAPI — hosts matches, auth, matchmaking      │
└─────────────────────┬───────────────────────────────┘
                      │ Python function calls
┌─────────────────────▼───────────────────────────────┐
│                  Rules Engine                       │
│    Pure Python — state + action → new state         │
│    No UI, no networking, no side effects            │
└─────────────────────┬───────────────────────────────┘
                      │ same engine
┌─────────────────────▼───────────────────────────────┐
│              RL Environment Wrapper                 │
│   Gymnasium/PettingZoo API — observation, step      │
└─────────────────────────────────────────────────────┘
```

**Key principle**: The Rules Engine is the foundation. The RL wrapper and the Game Server both use
the same engine code. Swapping the frontend or RL library never touches the engine.

---

## Technology Choices

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| Engine | Python | Fast to build, great RL ecosystem (Gymnasium, SB3, RLlib) |
| RL wrapper | Gymnasium + PettingZoo | Standard interface, compatible with most RL libraries |
| Server | FastAPI + WebSockets | Async, fast, easy to deploy |
| Frontend | React | Component model suits card game UI |
| Card/ruleset data | JSON / YAML | Human-readable, diff-friendly, no code changes for new sets |
| Testing | pytest | Deterministic game traces as golden-master tests |

### Future scaling path
If RL training throughput becomes a bottleneck, hot paths in the engine can be ported to
Rust via PyO3 bindings. Writing the engine as a pure state-transition function from day one
keeps this door open without requiring it now.

---

## Rules Engine — Design

### Core Principle
The engine is a **pure state-transition function**:

```
step(GameState, Action) -> GameState
```

No global state. No side effects. Given the same state, seed, and action, always produces
the same result. This is essential for:
- RL (reproducible training runs)
- Debugging (replay any game from any point)
- Testing (golden-master tests against known game logs)

### Five Core Components

#### 1. `GameState`
An immutable snapshot of everything needed to reconstruct the game at any point.

Contains:
- Both players' zones: deck, hand, life cards, Don!! area, character field, stage, trash
- Active player indicator
- Current phase (Refresh, Draw, Don!!, Main, End)
- Turn count
- Don!! state per card (active / rested / attached to character)
- Effect stack (for resolving triggered abilities)
- RNG state (seeded, deterministic)

**Immutability matters**: `step()` returns a new state rather than mutating the old one.
This makes parallelization trivial (RL vector envs), undo/replay free, and bugs easier to trace.

#### 2. `Action`
A typed, serializable description of one thing a player can do.

Action types:
- `PlayCard(card_id, don_attached, targets)`
- `AttachDon(card_id)`
- `DeclareAttack(attacker_id, target)`
- `DeclareCounter(card_id, power_bonus)`
- `DeclareBlocker(card_id)`
- `ActivateEffect(card_id, targets)`
- `PassPriority()`
- `Mulligan(cards_to_swap)`
- `EndPhase()`

Each action has typed parameters. The engine exposes `legal_actions(state) -> List[Action]`
which the RL environment and UI both use to enumerate what's currently possible.

#### 3. Effect DSL
The composable language for describing what cards do. This is the hardest and most important
design decision in the engine.

**Why a DSL?** With 1000+ cards and counting, writing a Python function per card is
unmaintainable and untestable. Instead, every card's behavior is expressed as pure data
(JSON) using a defined vocabulary of primitives. The engine interprets that data at runtime.

**Atomic effect primitives:**
```
Draw(n)
GivePower(target, amount, duration)
Search(zone, filter, count, destination)
KO(target)
MoveCard(card, from_zone, to_zone)
RestDon(n)
AddToDon(n)
AttachDon(target, n)
Trash(target)
Bounce(target)              # return to hand
LookAt(zone, n)             # look at top N of deck
```

**Combinators:**
```
Sequence([effect1, effect2, ...])     # do in order
Choice([effect1, effect2])            # player chooses one
Conditional(condition, effect)        # if X then Y
ForEach(target_set, effect)           # apply to each matching card
Optional(effect)                      # player may or may not activate
```

**Trigger types:**
```
OnPlay          # when this card is played from hand
WhenAttacking   # when this card declares an attack
OnKO            # when this card is KO'd
EndOfTurn       # at end of your turn
StartOfTurn     # at start of your turn
OnCounter       # when this card is used as a counter
```

**Example — card expressed as JSON data:**
```json
{
  "id": "OP01-060",
  "name": "Monkey D. Luffy",
  "type": "Character",
  "cost": 5,
  "power": 6000,
  "color": "Red",
  "counter": 1000,
  "keywords": ["Rush"],
  "triggers": [
    {
      "type": "OnPlay",
      "effect": {
        "op": "KO",
        "target": {
          "zone": "opponent_characters",
          "filter": "cost <= 5",
          "selection": "player_choice",
          "count": 1
        }
      }
    }
  ]
}
```

No Python. No logic. A contributor can add a new card by writing JSON only.

#### 4. Effect Stack + Resolution

OPTCG has triggered abilities, counter windows, and blocker interrupts that require a
priority system. Modeled as a stack:

- Effects are pushed onto the stack as they trigger
- Both players receive priority windows to respond
- Effects resolve LIFO (last in, first out)
- Each resolution step produces a new `GameState`

This handles complex interactions: "when X triggers during Y's resolution" nests cleanly
on the stack. Getting this right prevents an entire class of timing bugs.

Reference: MTG engines (Forge, XMage) use the same pattern. OPTCG is simpler but
structurally identical.

#### 5. `Ruleset`

A first-class object passed into every game. Contains:
- Version string (e.g., `"2025-Q1"`)
- Banlist: set of card IDs not legal to play
- Errata: map from card ID → corrected card definition (overrides base JSON)
- Interaction flags: toggles for contested rulings

Stored as YAML/JSON files. Immutable during a game. When Bandai issues a ruling,
a new ruleset file is created — the old one is never mutated.

**Why this matters for RL**: Training runs reference a specific ruleset version. 
Games trained under `2024-Q4` are fully reproducible even after `2025-Q1` is released.

---

## Data Layer — Card Database

### Separation of concerns

```
engine/           ← Python code only. Knows how to run games.
cards/            ← JSON data only. No code.
  OP01/
    OP01-001.json
    OP01-002.json
  ST01/
    ST01-001.json
rulesets/         ← JSON/YAML data only. No code.
  2024-q4.json
  2025-q1.json
```

The engine has zero knowledge of specific cards. It only knows how to interpret
card definitions expressed in the DSL vocabulary.

**Test of correct separation**: A contributor should be able to add an entire new card
set by writing JSON files only, without modifying any Python.

### Card images

Card images are NOT stored in the repository. They are:
- Fetched at runtime from the official OPTCG CDN via stored image IDs
- Cached locally after first fetch
- Loaded via a pluggable `ImageProvider` interface

This keeps the repo legally clean and allows the image source to be swapped
(e.g., point to a local folder, a different CDN, or a proxy) without engine changes.

---

## Ruleset Flow — How It All Connects

```
Deck validation (pre-game)
  deck_validate(deck, ruleset)
    └── checks card IDs against ruleset.banlist
    └── raises DeckValidationError if illegal

Game instantiation
  Game(player1_deck, player2_deck, ruleset, seed)
    └── loads card definitions from JSON
    └── applies ruleset.errata overlays
    └── creates DSLInterpreter(engine=self, ruleset=ruleset)

During play — effect resolution
  DSLInterpreter.resolve(effect_definition, card_id)
    └── checks ruleset.errata for this card_id
    └── uses errata definition if present, base JSON if not
    └── executes resolved effect tree against engine
```

The `Ruleset` object touches three places for three different reasons:
1. **Deck validation** — is this deck legal?
2. **Game setup** — apply errata overlays to card definitions
3. **Effect resolution** — use correct card definition under current rules

The `Game` object is the single source of truth for which ruleset is active.
Everything downstream inherits it from there.

---

## Versioning Strategy

### Rules versioning
- Each official Bandai ruling cycle → new ruleset file
- Ruleset files are append-only (never mutate old ones)
- Games store their ruleset version in the game record
- Old games are always replayable under the ruleset they were played with

### Card data versioning
- Base card definitions are immutable once added
- Errata live exclusively in ruleset files, not in card files
- Card IDs are stable (use official Bandai IDs: `OP01-001`, `ST01-002`, etc.)

### Ban list versioning
- Ban lists are arrays of card IDs inside ruleset files
- No code changes needed when a card is banned or unbanned

---

## Build Roadmap

Ordered by dependency — each step unblocks the next.

### Phase 1 — Engine (current focus)
1. Card data model and DSL schema design
2. `GameState` and zone management
3. Turn structure and phase loop
4. Action enumeration (`legal_actions`)
5. Effect DSL interpreter (atomic primitives first, then combinators)
6. Combat resolution (attack, counter, blocker windows)
7. Effect stack and trigger ordering
8. Win condition checking
9. Ruleset loading and errata overlay
10. Deck validation

**Milestone**: Two random bots play a complete, legal game end-to-end via CLI.

### Phase 2 — RL Environment
11. Gymnasium-compatible wrapper
12. Observation space encoding (state → tensor)
13. Action masking (critical — legal action space is sparse and variable)
14. PettingZoo multi-agent wrapper
15. Baseline heuristic bot (needed as RL training opponent)
16. Self-play training loop (PPO baseline)

**Milestone**: RL agent beats random bot reliably.

### Phase 3 — Web Product
17. React frontend — board, hand, zones
18. WebSocket game server (FastAPI)
19. Single-player vs bot
20. Multiplayer matchmaking
21. Deck builder
22. Accounts and persistence (Postgres + Auth.js)
23. Deployment (Fly.io or Railway to start)

---

## Repository Structure (planned)

```
optcg-sim/
├── engine/                 # Core rules engine (Python)
│   ├── game.py             # Game, GameState, turn loop
│   ├── actions.py          # Action types and parameters
│   ├── zones.py            # Deck, hand, field, life, trash
│   ├── combat.py           # Attack/counter/block resolution
│   ├── stack.py            # Effect stack and priority
│   ├── interpreter.py      # DSL interpreter
│   ├── ruleset.py          # Ruleset loading and errata
│   └── deck.py             # Deck validation
├── cards/                  # Card definitions (JSON, no code)
│   ├── OP01/
│   ├── OP02/
│   └── ST01/
├── rulesets/               # Ruleset versions (JSON/YAML)
│   ├── 2024-q4.json
│   └── 2025-q1.json
├── rl/                     # RL environment wrapper
│   ├── env.py              # Gymnasium env
│   ├── observation.py      # State → tensor encoding
│   └── agents/             # Heuristic and trained agents
├── server/                 # FastAPI game server
├── web/                    # React frontend
├── tests/
│   ├── engine/             # Unit tests per component
│   ├── integration/        # Full game trace tests
│   └── fixtures/           # Known game logs (golden masters)
└── docs/
    └── ARCHITECTURE.md     # This file
```

---

## Legal & Open Source Posture

- License: **Apache 2.0** (explicit patent grant, broad adoption)
- Card images: not in repo, fetched at runtime via pluggable provider
- Card mechanics/rules: not copyrightable, legally safe to implement
- Card names, text, artwork: Bandai IP — never stored in repo
- Prominent disclaimer: "Unofficial fan project. Not affiliated with or endorsed by Bandai."
- Non-commercial: do not monetize card access or game simulation directly
- Takedown-ready: image loading is behind a single interface — can be disabled in one PR

---

## Design Invariants

These should never be violated regardless of future changes:

1. `step(state, action) -> state` is a pure function. No mutation, no global state.
2. Given the same `(initial_state, seed, action_sequence)`, the game always produces the same result.
3. Card definitions are data. No per-card Python code.
4. The engine has no knowledge of UI, networking, or RL. It only knows game rules.
5. A new card set is a data task, not an engineering task.
6. A rules change is a new ruleset file, not a code change.
7. Old games are always replayable under the ruleset they were played with.
