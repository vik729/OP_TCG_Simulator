# Engine Vanilla MVP — Design Specification

> **Sub-project**: Rules engine to the "two random bots play a complete legal game end-to-end" milestone.
> **Approach**: Vanilla-first — no DSL, no triggered effects.
> **Date**: 2026-05-02
> **Status**: Approved design, ready for implementation planning.

---

## 1. Context

`OP_TCG_Simulator` is a long-term project to build a rules-complete simulator for the One Piece Trading Card Game. The eventual product is a four-layer system: rules engine → RL environment wrapper → game server → web frontend. The four layers are described in `docs/ARCHITECTURE.md`; this spec covers the **first sub-project** of the rules engine layer.

### Existing state (assumed by this spec)

- `engine/__init__.py`, `engine/game_state.py`, `engine/actions.py`, `engine/phase_machine.py` — foundational data model already built on branch `feat/game-state-engine` (uncommitted as of writing)
- `tests/test_game_state.py` — structural tests for the foundation
- `cards/ST01..ST04/*.json` — 68 normalized card definitions
- `cards/raw/decks/ST-01..04.json` — official starter deck contents
- `tools/fetch_cards.py`, `tools/normalize_cards.py`, `tools/audit_effects.py` — data pipeline
- `docs/ARCHITECTURE.md`, `docs/EFFECT_MAP.md`, `rule_comprehensive.md`, `docs/todos/DSL_PIPELINE.md`

### Out of scope for this spec

- DSL parser / triggered effects (deferred — see `docs/todos/DSL_PIPELINE.md` and new `docs/todos/EFFECT_TEXT_PARSER.md`)
- RL environment wrapper (Phase 2)
- Game server / frontend (Phase 3)
- Statistics aggregation (deferred — see new `docs/todos/STATS_AGGREGATION.md`)
- Smart keyword regex (deferred — see new `docs/todos/SMART_KEYWORD_REGEX.md`)

---

## 2. Goal & non-goals

### Goal

Bring the engine to a state where:

> `python -m engine.play --p1 ST-01 --p2 ST-02 --seed 42` runs to completion and prints a winner with a recorded `win_reason`. Hypothesis property tests across 100+ random seeds confirm termination, invariants, and determinism.

### Non-goals

- Triggered card effects (no `[On Play]`, no `[When Attacking]`, no `[On K.O.]`, etc.)
- Counter EVENTS (i.e., Event cards with `[Counter]` text). In-hand `counter` *value* on Character cards IS supported.
- `[Activate: Main]` abilities on Leaders or Characters — the action type stays in code but is rejected as illegal in vanilla mode.
- Conditional keywords like `[DON!! x2] [Rush]` — `conditional_keywords` field exists on `CardDefinition` but is empty for vanilla; condition evaluator is a stub
- Effect-granted keywords (L3) — `temp_keywords` field exists on `CardInstance` but nothing pushes onto it in vanilla
- Web UI, persistence beyond replay traces, multi-game stats

### What "vanilla" means precisely

A card has only:
- Its base stats (cost, power, counter, life, color, subtypes, attribute)
- The set of static keyword effects from rule §10-1: `Blocker`, `Rush`, `Rush:Character`, `Banish`, `Double Attack`, `Unblockable`
- A `keywords` tuple populated by the loader (regex + override)
- An empty `triggers` tuple
- An empty `conditional_keywords` tuple

The bot enacts all base game mechanics (turn loop, combat, life loss, deck-out, mulligan, DON economy) but never resolves triggered effects.

---

## 3. Locked design decisions

| Decision | Choice | Rationale |
|---|---|---|
| Sub-project scope | Engine to "two random bots play a legal game" milestone | Already in progress; foundation exists; clear stopping point |
| Effect handling | Vanilla-first (no DSL) | Engine is the bigger architectural risk; DSL design benefits from a working interpreter to plug into |
| Keywords in scope | All 6 static keywords from §10-1 + in-hand counter values | Each is ~5 LOC and makes the demo game look like real OPTCG |
| Game setup | Full §5 fidelity, mulligan via `pending_input` | Exercises the paused-engine pattern early on the only place it fires in vanilla |
| Random bot | Uniform random over `legal_actions`, 500-turn safety cap | Simplest correct policy; deck-out bounds game length naturally |
| Deck handling | Official ST01–04 decks from `cards/raw/decks/`; full validator (size/color/multiplicity/banlist) | Validator MUST ship in MVP because non-official decks will be tested very soon |
| Tests | Smoke + property tests (Hypothesis) | Property tests force structural correctness across random inputs; golden-master traces deferred |
| Phase advancement | Explicit `AdvancePhase()` action for each automatic phase | Every state change is a logged trace entry; future cards may modify phase behavior; `step()` stays simple |
| Persistence | Action-trace JSONL only (option 1); no per-step snapshots, no aggregate stats | Replay-from-trace + immutable state gives RL branching for free; per-step on disk is wasteful |
| Performance | `step()` target <100µs/call; treat `clone(state) = state` as canonical | Required for RL training (millions of step calls per training run) |
| Combat module | All 7 battle phases in one `combat.py` file | Cohesive; one entry point per action type; easy to test together |
| RNG separation | Game RNG (`state.rng_state`) is separate from bot RNG | Replay independent of bot policy; lets you swap policies without touching engine determinism |
| Keyword extraction | Hand-authored YAML per set + tiny regex fallback (override file empty initially) | Smart regex is a deferred, data-pattern-recognition task; manual is faster for 68 cards |

---

## 4. Architecture summary

The engine is a pure state-transition function:

```
step(GameState, Action) → GameState
```

- `GameState` is an immutable frozen dataclass tree (already exists in `engine/game_state.py`).
- `Action` is a frozen dataclass union (already exists in `engine/actions.py`); MVP adds `AdvancePhase`.
- `step()` validates the action, dispatches to a per-action handler, then runs win-condition checks.
- Every automatic phase requires an explicit `AdvancePhase()` action; the engine never auto-loops.
- The effect stack and resolver exist as plumbing but the resolver is a no-op stub (the stack is always empty in vanilla).
- Randomness is deterministic via a splittable seed pattern (`engine/rng.py`).

The four-layer separation (engine ↔ RL ↔ server ↔ frontend) from `ARCHITECTURE.md` is preserved: this spec touches **only the engine layer**.

---

## 5. Module map

### Existing files (modified in W1.1 only)

| File | Modification |
|---|---|
| `engine/game_state.py` | Add `WinReason` enum; add `winner` already exists; add `win_reason: Optional[WinReason] = None` field to `GameState`; update `validate_invariants` to assert `GAME_OVER ⇒ win_reason is not None` |
| `engine/actions.py` | Add `AdvancePhase` action (frozen dataclass, no params) |
| `engine/phase_machine.py` | Add `AdvancePhase` to `LEGAL_ACTIONS` for the **automatic phases only**: REFRESH, DRAW, DON, END, BATTLE_DECLARED, BATTLE_WHEN_ATK, BATTLE_DAMAGE, BATTLE_CLEANUP. `BATTLE_TRIGGER` stays as `{ActivateTrigger, PassTrigger}` (it is a defender decision phase). In vanilla, `BATTLE_TRIGGER` is never entered because no card has a parsed `[Trigger]` — the combat logic in BATTLE_DAMAGE transitions directly to BATTLE_CLEANUP when the revealed life card has no `triggers[]`. |
| `tests/test_game_state.py` | Add tests for new fields and `AdvancePhase` legality |

### New files (engine)

| File | Purpose | Approx. LOC |
|---|---|---|
| `engine/rng.py` | Splittable seed RNG: `split_rng(state: int) → (Random, int)` | ~30 |
| `engine/card_db.py` | `CardDefinition` dataclass; `CardDB` class to load `cards/STxx/*.json`; merge keyword YAML; lookup by ID | ~120 |
| `engine/keywords.py` | `effective_keywords(card, db, state) → frozenset[str]`; condition evaluator (vanilla: `[DON!! xN]` only) | ~40 |
| `engine/ruleset.py` | `Ruleset` frozen dataclass (id, banlist); `RULESETS` registry dict (vanilla MVP: one entry, `"ST01-ST04-v1"` with empty banlist) | ~25 |
| `engine/deck.py` | `DeckList` dataclass; `load_official_deck`; `load_custom_deck`; `validate_deck(deck, db, ruleset)` | ~120 |
| `engine/setup.py` | `build_initial_state(p1_deck: DeckList, p2_deck: DeckList, seed: int, ruleset: Ruleset, db: CardDB) → GameState`; SETUP-phase action handlers | ~150 |
| `engine/legal_actions.py` | `legal_actions(state) → tuple[Action, ...]` for every phase | ~200 |
| `engine/win_check.py` | `check_win_conditions(state) → state` — sets `win_reason`, transitions to `GAME_OVER` | ~50 |
| `engine/combat.py` | All 7 battle sub-phase handlers + `begin_attack()` entry from MAIN | ~250 |
| `engine/resolver.py` | Stub: `resolve_top(state) → state`; empty stack → no-op; non-empty raises `NotImplementedError` | ~15 |
| `engine/replay.py` | `record_action`, `save_trace`, `load_trace`, `replay(trace, until_turn=None)` | ~100 |
| `engine/step.py` | `step(state, action) → state` dispatcher; per-action handlers (delegates combat to `combat.py`) | ~250 |
| `engine/bots/__init__.py` | Empty package marker | 1 |
| `engine/bots/random_bot.py` | `random_legal_action(state, rng) → Action` | ~20 |
| `engine/play.py` | CLI: argparse, `--p1`, `--p2`, `--seed`, `--bot-seed`, `--log`, `--replay`, `--verbose`, `--until-turn` | ~120 |

### New files (data)

| File | Purpose |
|---|---|
| `cards/keywords/ST01.yaml` | Hand-authored keyword data for ST01 cards (one entry per card; empty list for vanilla cards) |
| `cards/keywords/ST02.yaml` | Same for ST02 |
| `cards/keywords/ST03.yaml` | Same for ST03 |
| `cards/keywords/ST04.yaml` | Same for ST04 |
| `cards/keyword_overrides.yaml` | Currently empty; reserved for future override entries when smart regex lands |

### New files (tests)

| File | Type |
|---|---|
| `tests/test_rng.py` | unit |
| `tests/test_card_db.py` | unit |
| `tests/test_keywords.py` | unit |
| `tests/test_ruleset.py` | unit |
| `tests/test_deck.py` | unit |
| `tests/test_setup.py` | unit |
| `tests/test_legal_actions.py` | unit |
| `tests/test_win_check.py` | unit |
| `tests/test_combat.py` | unit |
| `tests/test_step.py` | unit |
| `tests/test_resolver.py` | unit |
| `tests/test_replay.py` | unit |
| `tests/test_random_bot.py` | unit |
| `tests/test_random_game.py` | smoke + property |

### New files (docs/todos)

| File | Captures |
|---|---|
| `docs/todos/SMART_KEYWORD_REGEX.md` | Position-aware keyword extractor, deferred until the data-pattern-recognition pass can run against the full card DB |
| `docs/todos/EFFECT_TEXT_PARSER.md` | Full text-to-DSL parser (subsumes SMART_KEYWORD_REGEX); handles `{}`/`<>`/`[]` bracket disambiguation; produces filter dicts |
| `docs/todos/STATS_AGGREGATION.md` | Win-rate / matchup / first-vs-second analysis; per-batch CSV output; bundled with RL phase |
| `docs/todos/PERFORMANCE_PROFILING.md` | <100µs/step target; turn-boundary memo cache as escape hatch if profiling shows replay is the bottleneck for RL |

---

## 6. Dependency graph

```
                              play.py
                                 │
                       ┌─────────┴─────────┐
                  random_bot.py          step.py
                       │                    │
                       └─── legal_actions.py┴─────┐
                                  │               │
                              combat.py       win_check.py
                                  │               │
                                step.py ──────────┘
                                  │
                              resolver.py (stub)
                                  │
                              setup.py ── replay.py
                                  │
                              keywords.py
                                  │
                              card_db.py ── deck.py ── ruleset.py
                                  │
                              game_state.py + actions.py + phase_machine.py
                                  │
                                rng.py
```

**Isolation properties** (verified):
- `rng.py`, `card_db.py`, `win_check.py`, `resolver.py`, `replay.py`, `keyword YAMLs`, schema additions are leaves with no inter-dependencies. **Seven sub-agents can build these in parallel.**
- `deck.py`, `keywords.py`, `setup.py`, `legal_actions.py` are mid-layer with single dependencies on leaves.
- `combat.py`, `step.py` are sequential within the engine core.
- `random_bot.py`, `play.py` are glue.

---

## 7. Engine internals

### 7.1 The `step()` pattern

```python
def step(state: GameState, action: Action) -> GameState:
    if not is_legal_action(state.phase, action, state.is_waiting_for_input()):
        raise IllegalActionError(...)
    new_state = _ACTION_HANDLERS[type(action)](state, action)
    new_state = check_win_conditions(new_state)
    return new_state
```

There is no auto-advance loop. Every phase transition is its own step. Callers must invoke `step(state, AdvancePhase())` to traverse automatic phases — `legal_actions(state)` returns `(AdvancePhase(),)` for those phases as the only option.

The dispatch table at the top of `step.py`:

```python
_ACTION_HANDLERS = {
    ChooseFirst:      _handle_choose_first,
    RespondInput:     _handle_respond_input,
    AdvancePhase:     _handle_advance_phase,
    PlayCard:         _handle_play_card,
    AttachDon:        _handle_attach_don,
    DeclareAttack:    combat.begin_attack,
    DeclareBlocker:   combat.handle_blocker,
    PassBlocker:      combat.handle_pass_blocker,
    PlayCounter:      combat.handle_counter,
    PassCounter:      combat.handle_pass_counter,
    ActivateTrigger:  combat.handle_trigger,        # vanilla: never reached
    PassTrigger:      combat.handle_pass_trigger,
    ActivateAbility:  _handle_activate_ability,     # vanilla: raises NotImplementedError; never reached because legal_actions doesn't offer it for vanilla cards
    EndTurn:          _handle_end_turn,
}
```

`_handle_advance_phase` dispatches further by current phase to perform that phase's logic (e.g., REFRESH unrests cards, DRAW draws a card, DON adds 2 DON, END advances turn).

### 7.2 Combat sub-phase machine

Combat lives entirely in `combat.py`. Entry point is `combat.begin_attack(state, DeclareAttack)` from MAIN.

| Phase | Driver | Action | What happens (vanilla) |
|---|---|---|---|
| `BATTLE_DECLARED` | auto | `AdvancePhase()` | Rest attacker, set `battle_context`, → `BATTLE_WHEN_ATK` |
| `BATTLE_WHEN_ATK` | auto | `AdvancePhase()` | No-op (no triggers in vanilla), → `BATTLE_BLOCKER` |
| `BATTLE_BLOCKER` | defender | `DeclareBlocker(id)` or `PassBlocker()` | If attacker has `[Unblockable]`, only `PassBlocker()` is legal. Blocker character is rested; battle target is redirected to the blocker. → `BATTLE_COUNTER` |
| `BATTLE_COUNTER` | defender | `PlayCounter(id)` (loop) or `PassCounter()` | Each `PlayCounter` trashes the played card and adds its `counter` value to `battle_context.power_boosts`. Loops until `PassCounter()`. → `BATTLE_DAMAGE` |
| `BATTLE_DAMAGE` | auto | `AdvancePhase()` | Compute final attacker power (base + DON × 1000 + temp_effects). Compute final target power (base + DON × 1000 + counter sum). If atk ≥ target: target loses (Leader → 1 life, Character → K.O.); if atk < target: nothing. Apply `[Double Attack]` (2 life), `[Banish]` (life trashed, no Trigger). Then check the revealed life card (if any): if it has parsed `triggers[]` → `BATTLE_TRIGGER`; else → `BATTLE_CLEANUP`. **In vanilla, `triggers[]` is always empty so this always goes to `BATTLE_CLEANUP` — `BATTLE_TRIGGER` is never entered.** |
| `BATTLE_TRIGGER` | defender | `ActivateTrigger()` or `PassTrigger()` | Defender chooses to activate or skip the [Trigger]. Vanilla never reaches this phase. → `BATTLE_CLEANUP` |
| `BATTLE_CLEANUP` | auto | `AdvancePhase()` | Clear `battle_context`; expire `TempEffect`s with `expires_after=BATTLE_CLEANUP`; → `MAIN` |

### 7.3 Setup flow

`setup.build_initial_state(p1_deck: DeckList, p2_deck: DeckList, seed: int, ruleset: Ruleset, db: CardDB) → GameState` returns a state in `Phase.SETUP` with:
- Both decks loaded into the deck zone (unshuffled)
- No hands, no life cards
- `active_player_id = None` (not yet determined)
- `pending_input = None`
- Awaiting `ChooseFirst("P1" | "P2")`

The setup procedure runs through the normal `step()` loop:

```
step(SETUP, ChooseFirst("P1"))
  → shuffle both decks (consumes RNG)
  → set active_player_id = P1
  → deal 5 cards to each hand
  → create pending_input asking P1 about mulligan ("yes" | "no")

step(SETUP, RespondInput(("yes",)))
  → P1's hand → deck, reshuffle, deal 5 again
  → create pending_input asking P2 about mulligan

step(SETUP, RespondInput(("no",)))
  → P2 keeps hand
  → deal life cards: top of deck → bottom of life (per §5-2-1-7)
  → transition to REFRESH (turn=1)

step(REFRESH, AdvancePhase())
  → no-op on turn 1 (no rested cards)
  → → DRAW

step(DRAW, AdvancePhase())
  → P1 does NOT draw on turn 1 (per §6-3-1)
  → → DON

step(DON, AdvancePhase())
  → place 1 DON card (not 2, per §6-4-1) face-up in cost area
  → → MAIN
```

Now ready for P1's first action. Bot's `ChooseFirst` and mulligan responses come from `random_legal_action(state)` like any other action — no special "bot in setup" code path.

### 7.4 Three-level keyword model

Every "does this card have keyword X?" query goes through one function:

```python
def effective_keywords(card: CardInstance, db: CardDB, state: GameState) -> frozenset[str]:
    definition = db.get(card.definition_id)
    result = set(definition.keywords)                                          # L1: innate always-on
    for grant in definition.conditional_keywords:                              # L2: innate conditional
        if _evaluate_condition(grant.condition, card, state):
            result.add(grant.keyword)
    result.update(tk.keyword for tk in card.temp_keywords)                     # L3: runtime grants
    return frozenset(result)
```

| Level | Source | Vanilla state |
|---|---|---|
| L1: innate always-on | `CardDefinition.keywords` (loaded from YAML + regex) | Populated for ~15 cards in ST01–04 |
| L2: innate conditional | `CardDefinition.conditional_keywords` | Empty for all vanilla cards (no card has `[DON!! xN] [Keyword]`) |
| L3: runtime grants | `CardInstance.temp_keywords` | Empty (no resolver to push grants) |

Conditional evaluator (`engine/keywords.py`) handles only `{"type": "don_attached_min", "value": N}` in vanilla. Stub for other condition types raises `NotImplementedError`.

### 7.5 RNG plumbing

```python
def split_rng(rng_state: int) -> tuple[random.Random, int]:
    rng = random.Random(rng_state)
    next_state = rng.randint(0, 2**63 - 1)
    return rng, next_state
```

Used like:

```python
rng, new_rng_state = split_rng(state.rng_state)
shuffled = tuple(rng.sample(state.p1.deck, len(state.p1.deck)))
new_state = dataclasses.replace(state, rng_state=new_rng_state, p1=...)
```

Determinism property: same starting `rng_state` + same action sequence → bit-identical state trace.

The bot has its own separate RNG seeded independently. The bot's RNG state is NOT in `GameState` — it's owned by the caller (e.g., `play.py` holds it). This way, replaying a recorded trace (which records actions, not bot RNG state) is independent of bot determinism.

### 7.6 Card DB

```python
@dataclass(frozen=True)
class ConditionalKeywordGrant:
    keyword: str
    condition: dict   # e.g., {"type": "don_attached_min", "value": 2}

@dataclass(frozen=True)
class CardDefinition:
    id: str
    name: str
    type: str           # "Leader" | "Character" | "Event" | "Stage"
    color: tuple[str, ...]
    cost: Optional[int]
    power: Optional[int]
    counter: Optional[int]
    life: Optional[int]
    attribute: Optional[str]
    subtypes: tuple[str, ...]
    keywords: tuple[str, ...]
    conditional_keywords: tuple[ConditionalKeywordGrant, ...]
    triggers: tuple[dict, ...]
    effect_text: str

class CardDB:
    def __init__(self, cards_root: Path = Path("cards")) -> None: ...
    def get(self, definition_id: str) -> CardDefinition: ...
    def all_definitions(self) -> Iterator[CardDefinition]: ...
```

**Loading process** (per card JSON):
1. Read `cards/STxx/{card_id}.json`.
2. Convert lists → tuples for immutability.
3. Resolve keywords:
   - Read `cards/keywords/{set_id}.yaml`. The card's entry in this file is the authoritative `keywords` tuple.
   - If no entry exists, fall back to naive regex: scan `effect_text` for `[Blocker]`, `[Rush]`, `[Banish]`, `[Double Attack]`, `[Unblockable]`, `[Rush: Character]`.
   - Apply `cards/keyword_overrides.yaml` last (currently empty; format documented inline in the file).
4. `conditional_keywords = ()` (vanilla).
5. `triggers = ()` (vanilla).
6. Build `CardDefinition`.

### 7.7 Deck

```python
@dataclass(frozen=True)
class DeckList:
    leader_id: str
    main_deck_ids: tuple[str, ...]   # 50 entries, duplicates per multiplicity
    don_count: int = 10

class DeckValidationError(Exception): ...

def load_official_deck(deck_id: str, db: CardDB) -> DeckList:
    """Load from cards/raw/decks/ST-XX.json. Returns a validated DeckList."""

def load_custom_deck(path: Path, db: CardDB) -> DeckList:
    """Load from a YAML decklist file. Returns a validated DeckList."""

def validate_deck(deck: DeckList, db: CardDB, ruleset: Ruleset) -> None:
    """Raises DeckValidationError on first violation."""
```

Custom deck format (YAML):

```yaml
leader: ST01-001
main_deck:
  - {id: ST01-002, count: 4}
  - {id: ST01-003, count: 3}
```

**Validation rules** (raise on first failure):
1. Leader card has `type == "Leader"`.
2. `len(main_deck_ids) == 50`.
3. Color rule (§5-1-2-2): every main-deck card's color set is a subset of the leader's color set.
4. Multiplicity (§5-1-2-3): `Counter(main_deck_ids).most_common(1)[0][1] <= 4`.
5. Banlist: no card_id is in `ruleset.banlist`.
6. Existence: every card_id resolves in `db`.

**`Ruleset` for vanilla MVP** (lives in `engine/ruleset.py`):

```python
@dataclass(frozen=True)
class Ruleset:
    id: str
    banlist: frozenset[str] = frozenset()

RULESETS: dict[str, Ruleset] = {
    "ST01-ST04-v1": Ruleset(id="ST01-ST04-v1", banlist=frozenset()),
}
```

The `id` field is what gets written into `GameState.ruleset_id`. Errata overlay deferred (see `docs/todos/DSL_PIPELINE.md`).

### 7.8 Replay

Trace format (JSONL, one record per line):

```jsonl
{"type":"header","schema":1,"seed":42,"bot_seed":7,"p1_deck":"ST-01","p2_deck":"ST-02","ruleset_id":"ST01-ST04-v1","timestamp":"2026-05-02T12:00:00Z"}
{"type":"action","turn":1,"phase":"setup","actor":"P1","action":{"_type":"ChooseFirst","first_player_id":"P1"}}
{"type":"action","turn":1,"phase":"setup","actor":"P1","action":{"_type":"RespondInput","choices":["no"]}}
...
{"type":"result","winner":"P1","win_reason":"LIFE_AND_LEADER_HIT","turns":14}
```

API:

```python
def record_action(trace: list[dict], state: GameState, action: Action) -> None: ...
def save_trace(trace: list[dict], path: Path, header_meta: dict) -> None: ...
def load_trace(path: Path) -> list[dict]: ...
def replay(trace: list[dict], db: CardDB, until_turn: Optional[int] = None) -> GameState: ...
```

Trace is built by `play.py` as the game progresses; the engine itself stays pure (no I/O).

### 7.9 Random bot

```python
def random_legal_action(state: GameState, rng: random.Random) -> Action:
    actions = legal_actions(state)
    if not actions:
        raise NoLegalActionsError(f"No legal actions in {state.phase}")
    return rng.choice(actions)
```

The intelligence is entirely in `legal_actions(state)`.

### 7.10 Win check

```python
class WinReason(Enum):
    LIFE_AND_LEADER_HIT = "life_and_leader_hit"
    DECK_OUT = "deck_out"
    CONCESSION = "concession"           # not used in MVP
    CARD_EFFECT = "card_effect"          # not used in MVP

def check_win_conditions(state: GameState) -> GameState:
    """Called after every step(). If a defeat condition is met, returns a state in
    GAME_OVER with winner and win_reason set. Otherwise returns state unchanged."""
```

Vanilla MVP only ever produces `LIFE_AND_LEADER_HIT` or `DECK_OUT`.

### 7.11 CLI

```bash
# New game
python -m engine.play --p1 ST-01 --p2 ST-02 --seed 42 [--bot-seed 7] [--log path.jsonl] [--verbose]

# Replay existing trace
python -m engine.play --replay path.jsonl [--until-turn N] [--verbose]
```

Verbose output: phase transitions, every action taken, current life/hand/DON counts. Quiet output: just the final result line (`Winner: P1 (LIFE_AND_LEADER_HIT) — 14 turns`).

---

## 8. Test plan

### 8.1 Unit test inventory

(Each lives in its corresponding `tests/test_*.py` — module-by-module coverage. See module map §5 for the full list.)

### 8.2 Property tests (the milestone)

All in `tests/test_random_game.py`:

```python
import pytest
from hypothesis import given, settings, strategies as st
import random
from engine.card_db import CardDB
from engine.ruleset import RULESETS
from engine.deck import load_official_deck
from engine.setup import build_initial_state
from engine.step import step
from engine.bots.random_bot import random_legal_action
from engine.game_state import validate_invariants

@pytest.fixture(scope="module")
def db():
    return CardDB()

@pytest.fixture(scope="module")
def ruleset():
    return RULESETS["ST01-ST04-v1"]

def _run_full_game(seed: int, db: CardDB, ruleset) -> "GameState":
    p1_deck = load_official_deck("ST-01", db)
    p2_deck = load_official_deck("ST-02", db)
    state = build_initial_state(p1_deck, p2_deck, seed=seed, ruleset=ruleset, db=db)
    bot_rng = random.Random(seed + 100_000)
    while not state.is_terminal():
        action = random_legal_action(state, bot_rng)
        state = step(state, action)
    return state

@given(seed=st.integers(0, 1000))
@settings(max_examples=100, deadline=None)
def test_termination_and_invariants(seed, db, ruleset):
    p1_deck = load_official_deck("ST-01", db)
    p2_deck = load_official_deck("ST-02", db)
    state = build_initial_state(p1_deck, p2_deck, seed=seed, ruleset=ruleset, db=db)
    bot_rng = random.Random(seed + 100_000)
    while not state.is_terminal():
        action = random_legal_action(state, bot_rng)
        state = step(state, action)
        validate_invariants(state)
        assert state.turn_number < 500, f"runaway at seed={seed}"
    assert state.winner is not None
    assert state.win_reason is not None

@given(seed=st.integers(0, 1000))
@settings(max_examples=50, deadline=None)
def test_determinism(seed, db, ruleset):
    state_a = _run_full_game(seed, db, ruleset)
    state_b = _run_full_game(seed, db, ruleset)
    assert state_a == state_b

@given(seed=st.integers(0, 1000))
@settings(max_examples=50, deadline=None)
def test_card_count_conserved(seed, db, ruleset):
    """At every step, both players have exactly 51 cards in total."""
    p1_deck = load_official_deck("ST-01", db)
    p2_deck = load_official_deck("ST-02", db)
    state = build_initial_state(p1_deck, p2_deck, seed=seed, ruleset=ruleset, db=db)
    bot_rng = random.Random(seed + 100_000)
    while not state.is_terminal():
        action = random_legal_action(state, bot_rng)
        state = step(state, action)
        assert len(state.p1.all_cards()) == 51
        assert len(state.p2.all_cards()) == 51
```

When a property test fails, the failing seed is logged. A small helper writes the trace to `tests/fixtures/failures/{seed}.jsonl` for permanent reproduction.

### 8.3 Smoke test

```python
def test_smoke_random_game(db, ruleset):
    p1_deck = load_official_deck("ST-01", db)
    p2_deck = load_official_deck("ST-02", db)
    state = build_initial_state(p1_deck, p2_deck, seed=42, ruleset=ruleset, db=db)
    bot_rng = random.Random(7)
    while not state.is_terminal():
        action = random_legal_action(state, bot_rng)
        state = step(state, action)
    assert state.winner in (PlayerID.P1, PlayerID.P2)
    assert state.win_reason is not None
```

---

## 9. Sub-agent task decomposition

The work breaks into 4 waves. Within a wave, tasks have **no file conflicts** and can be dispatched to parallel sub-agents. Between waves, hard dependencies must be respected.

### Wave 1 — Schema additions and leaf modules (7 parallel tasks)

| ID | Task | Files created/modified | Acceptance |
|---|---|---|---|
| **W1.1** | Schema additions | `engine/game_state.py` (add `WinReason` enum with values `LIFE_AND_LEADER_HIT`, `DECK_OUT`, `CONCESSION`, `CARD_EFFECT`; add `win_reason: Optional[WinReason] = None` field to `GameState`; update `validate_invariants` to assert `GAME_OVER ⇒ win_reason is not None`); `engine/actions.py` (add `AdvancePhase` frozen dataclass, no params); `engine/phase_machine.py` (add `AdvancePhase` to `LEGAL_ACTIONS` for the **automatic phases only**: REFRESH, DRAW, DON, END, BATTLE_DECLARED, BATTLE_WHEN_ATK, BATTLE_DAMAGE, BATTLE_CLEANUP — NOT BATTLE_TRIGGER); `tests/test_game_state.py` updates | Existing tests pass; new fields covered; `AdvancePhase` legality checked for each phase |
| **W1.2** | RNG | `engine/rng.py`, `tests/test_rng.py` | `split_rng()` deterministic, advances state, returns distinct sub-RNGs on consecutive calls |
| **W1.3** | Replay | `engine/replay.py`, `tests/test_replay.py` | Round-trip works; trace format matches §7.8 |
| **W1.4** | Resolver stub | `engine/resolver.py`, `tests/test_resolver.py` | Empty stack passes through; non-empty raises `NotImplementedError` |
| **W1.5** | Win check | `engine/win_check.py`, `tests/test_win_check.py` | Both defeat conditions detected; sets `win_reason`; transitions to `GAME_OVER` |
| **W1.6** | Keyword YAMLs + TODOs | `cards/keywords/ST01.yaml`..`ST04.yaml`; `cards/keyword_overrides.yaml` (empty with header comment); `docs/todos/SMART_KEYWORD_REGEX.md`; `docs/todos/EFFECT_TEXT_PARSER.md`; `docs/todos/STATS_AGGREGATION.md`; `docs/todos/PERFORMANCE_PROFILING.md` | One YAML entry per card across ST01–04 (68 entries); each TODO file captures the deferred problem with enough context to pick up later |
| **W1.7** | Card DB | `engine/card_db.py`, `engine/keywords.py` (the `effective_keywords` + condition evaluator), `tests/test_card_db.py`, `tests/test_keywords.py` | Loads all 68 cards; keyword YAML applied; `effective_keywords` correctly unions L1/L2/L3 (L2/L3 empty in vanilla — verify the field exists and is read) |

> **File conflict check:** W1.1 modifies pre-existing engine files. All other Wave 1 tasks create new files. No conflicts.

### Wave 2 — Mid-layer (3 parallel tasks)

| ID | Task | Files | Depends on | Acceptance |
|---|---|---|---|---|
| **W2.1** | Deck + Ruleset | `engine/ruleset.py` (the `Ruleset` dataclass + `RULESETS` registry per §7.7); `engine/deck.py`; `tests/test_deck.py`; `tests/test_ruleset.py` | W1.7 | All 5 validation rules covered (happy + error case each); both loaders work; rejects deck with wrong color, 5 of one card, banned card; `RULESETS["ST01-ST04-v1"]` resolves |
| **W2.2** | Setup | `engine/setup.py`, `tests/test_setup.py` | W1.2, W1.7, W2.1 | `build_initial_state` produces valid state in `Phase.SETUP`; `ChooseFirst` shuffles + deals; mulligan flow works; life cards in correct order; auto-phases (REFRESH/DRAW/DON) correctly handle turn-1 special cases |
| **W2.3** | Legal actions | `engine/legal_actions.py`, `tests/test_legal_actions.py` | W1.7, W1.1, `engine/keywords.py` | Returns `(AdvancePhase(),)` for auto-phases; covers all action types per phase; affordability filter correct; turn-1 attack restriction; `[Rush]` unlocks turn-of-play attacks; no illegal actions ever returned |

### Wave 3 — Engine core (sequential within wave)

| ID | Task | Files | Depends on | Acceptance |
|---|---|---|---|---|
| **W3.1** | Combat | `engine/combat.py`, `tests/test_combat.py` | W2.3, W1.5, `keywords.py` | All 7 battle phases transition correctly; `[Blocker]` redirects target; `[Unblockable]` skips block step; counter values from hand accumulate; `[Double Attack]` deals 2 to leader; `[Banish]` trashes life with no Trigger; vanilla `BATTLE_TRIGGER` always passes |
| **W3.2** | Step dispatcher | `engine/step.py`, `tests/test_step.py` | W3.1, W2.2, W1.4, W1.5 | Every action type has a handler; illegal actions raise; pending-input gate enforced; calls `check_win_conditions` after every step; `_handle_advance_phase` dispatches by current phase |

### Wave 4 — Driver + integration

| ID | Task | Files | Depends on | Acceptance |
|---|---|---|---|---|
| **W4.1** | Random bot | `engine/bots/__init__.py`, `engine/bots/random_bot.py`, `tests/test_random_bot.py` | W2.3 | Uniform random over `legal_actions`; deterministic with seed; raises on no legal actions |
| **W4.2** | CLI + integration tests | `engine/play.py`, `tests/test_random_game.py` | W3.2, W4.1, W1.3 | Smoke test passes; all property tests pass with `max_examples >= 100`; CLI runs to completion; replay round-trip works end-to-end |

### Sub-agent task spec template

Each task spec for a sub-agent must include:

1. **Inputs**: list of files to read; reference sections in `rule_comprehensive.md` / `docs/ARCHITECTURE.md` / this spec
2. **Outputs**: list of files to create/modify (no others)
3. **Acceptance criteria**: specific tests that must pass; specific behaviors asserted
4. **Out of scope**: what NOT to do (explicit list of negatives — e.g., "don't add DSL parsing", "don't modify game_state.py beyond the listed fields")
5. **Done signal**: all listed tests pass; `mypy engine/` runs clean; the dependent task can start

---

## 10. Acceptance criteria for the MVP milestone

The engine MVP is **done** when *all* of these hold:

1. **CLI runs end-to-end**: `python -m engine.play --p1 ST-01 --p2 ST-02 --seed 42 --verbose` exits 0 with a winner and `win_reason`.
2. **All tests pass**: `pytest tests/ -v` is green, including all 14 test files listed in §5.
3. **Property tests survive 100+ random seeds** with `max_examples=100` per Hypothesis run.
4. **Deck validator rejects invalid decks** with specific error messages (wrong color, 5 of one card, banned card).
5. **Replay round-trip works**: any game's trace can be saved and re-played to a bit-identical final state.
6. **No DSL/triggered-effect code present**: `resolver.py` is the stub; no card has a populated `triggers[]`. (Negative criterion — confirms scope discipline.)
7. **`docs/todos/` populated** with the 4 deferred-work files listed in §5.

---

## 11. Performance targets

`step()` target: **<100 µs per call** on a typical mid-game state (50-card decks, 3–5 characters per side). This is the load-bearing constraint for RL training (millions of `step()` calls per training run).

Implementation guidance:
- Avoid copying full tuples when only one element changes — build new tuples by slicing, not list-comprehending the unchanged portion.
- `validate_invariants()` runs in tests only, never in production hot paths.
- The dispatch table in `step.py` is a `dict[type, Callable]` lookup, not an `if/elif` chain.
- `legal_actions(state)` returns a tuple, not a generator — RL agents need to iterate twice.

If profiling shows `replay()` is the bottleneck for RL, see `docs/todos/PERFORMANCE_PROFILING.md` for the turn-boundary memo cache approach.

---

## 12. Deferred / Out of scope

Each item below has its own `docs/todos/` file with full context. Listed here so nothing gets lost.

| Topic | Where it's tracked | Why deferred |
|---|---|---|
| Triggered card effects (DSL) | `docs/todos/DSL_PIPELINE.md` (existing) | Engine architecture must stabilize first |
| Smart keyword regex | `docs/todos/SMART_KEYWORD_REGEX.md` (new) | Requires data-pattern-recognition pass against full card DB; manual YAML faster for 68 cards |
| Effect text parser (full DSL) | `docs/todos/EFFECT_TEXT_PARSER.md` (new) | Subsumes smart keyword regex; central problem of DSL phase |
| Stats aggregation | `docs/todos/STATS_AGGREGATION.md` (new) | Belongs with RL phase; needs to know what stats matter |
| Performance profiling + memo cache | `docs/todos/PERFORMANCE_PROFILING.md` (new) | Premature optimization; profile first |
| Counter Event cards | (covered by DSL_PIPELINE) | They have effects; require DSL |
| `[Activate: Main]` Leader/Character abilities | (covered by DSL_PIPELINE) | They have effects; require DSL |
| Errata overlay in Ruleset | Future | No errata to apply yet |
| Concession action | Future | Not needed for bot vs bot |
| Three-or-more-player games | (rules §1-1-1 explicitly excludes) | Out of scope per rules |

---

## 13. Risks & mitigations

| Risk | Mitigation |
|---|---|
| `legal_actions()` returns an illegal action — bot crashes engine | Property tests run 100+ random games; any illegal action immediately fails a test. Each new action type added to `legal_actions` requires a test in `test_legal_actions.py`. |
| `legal_actions()` misses a legal action — bot is silently restricted | Manual cross-reference of each phase's allowed action types in `phase_machine.LEGAL_ACTIONS` against the enumerator's output. |
| Combat sub-phase logic gets the order wrong (e.g., counter resolved before block) | `combat.py` has 7 explicit transition functions; each tested independently. The phase machine in `phase_machine.PHASE_ORDER` is the source of truth for ordering. |
| Determinism breaks (e.g., dict iteration order, time-based RNG) | `test_determinism` property test runs 50 seeds, comparing two full game traces for bit-equality. |
| Card counts leak (e.g., a card disappears after PlayCard) | `validate_invariants()` runs after every step in property tests; immediately catches drift. |
| Mulligan `pending_input` flow is broken | `test_setup.py` exercises both yes and no cases for both players. |
| Performance regresses below 100µs/step | A microbenchmark in `tests/test_random_game.py` records `step()` p50/p99; if p99 > 200µs, test fails (warn-only initially, hard-fail once stable). |

---

## 14. References

- `docs/ARCHITECTURE.md` — high-level four-layer architecture
- `rule_comprehensive.md` — the comprehensive rules (§§1–11)
- `docs/EFFECT_MAP.md` — auto-generated audit of effect_text patterns across ST01–04
- `docs/todos/DSL_PIPELINE.md` — deferred DSL parser plan
- `README.md` — repo overview and roadmap

---

*End of spec.*
