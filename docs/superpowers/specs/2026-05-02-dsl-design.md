# OP TCG DSL Design

> **Status:** Brainstormed 2026-05-02. Awaiting plan.
> **Predecessor:** `2026-05-02-engine-vanilla-mvp-design.md` (engine MVP, complete)
> **Successor:** Implementation plan (writing-plans skill, after user approval)

## 1. Goal

Replace the engine's vanilla scope (static keywords + counter values only) with a domain-specific language that lets cards express triggered effects (Draw, KO, GivePower, AttachDon, …) plus the temporal scoping needed by real OPTCG mechanics. Keep the engine pure-functional, immutable, and replay-deterministic.

The DSL is *interpreter-driven*: card YAML is the source of truth, the resolver walks it, and the engine never executes Python card-effect code. This keeps replays portable and the engine free of card-specific branching.

## 2. Approach (Option A — DSL-first)

Hand-author DSL YAML for a small gold set, build the resolver against it, then scale via LLM-assisted authoring with human review. The text-to-YAML auto-parser is **not** part of v1; it remains a future possibility once the DSL is stable enough to parse into.

This sidesteps the riskiest piece of the original `EFFECT_TEXT_PARSER.md` plan (writing a regex parser for English card text) by replacing it with: hand-author the gold set + use Claude as a one-time authoring tool + commit YAML as runtime truth.

### 2.1 Iterative batch loop

The DSL grammar isn't locked in v1 — it grows through three batches, each refining the schema based on what the cards in that batch demand:

- **Batch A (v1)** — 5–10 hand-authored cards from ST01–02. Establishes the DSL primitive set, resolver mechanics, and the gold-standard YAML format. Triggers covered: `[On Play]`, `[When Attacking]`. Effects: enough to express the chosen 5–10 cards.
- **Batch B (v2)** — full ST01–04 (~50 cards), LLM-assisted with Batch A as few-shot examples. Adds DSL primitives that ST03/ST04 demand (almost certainly `[End of Your Turn]` for the Kaido deck, possibly `[Activate: Main]` and life-card `[Trigger]`).
- **Batch C (v3)** — OP-01, OP-02, eventually all sets. Adds static/continuous effects (Stage cards), niche modifications, anything else surfaced.

Each batch ends with: updated DSL spec, YAML for the batch's cards, resolver code for any new primitives, updates to `docs/dsl/CHANGELOG.md`, all committed atomically.

### 2.2 Card-loading is YAML-gated

The engine refuses to load any card whose `dsl_status` isn't `"vanilla"` (no effects) or `"parsed"` (YAML authored and validated). Cards with raw effect text but no authored YAML cause deck-load to fail with a clear error. This means:

- The engine never best-guesses an effect.
- A YAML file is the only thing that makes a card playable.
- We always know which cards have been authored vs. queued.

### 2.3 No YAML versioning field

DSL grammar and resolver evolve together in the same repo, never apart. Replays reference `card_id` strings; if Bandai issues errata, we create a new card_id (e.g., `ST01-001-errata-2025-03`) rather than mutating the existing one. Old replays still work because they reference the original card_id, which still exists.

## 3. DSL vocabulary

Two layers: *operators* (what to do) and *filters* (which cards to do it to). The filter sub-language is the lever that gives us archetype generality — one filter shape composes into KO targets, GivePower targets, ForEach loops, and conditional checks.

### 3.1 Operators (effect verbs) — v1 set

| Operator | Shape |
|---|---|
| `Draw` | `{count: N}` |
| `KO` | `{target: <filter>}` |
| `GivePower` | `{target: <filter>, amount: ±N, applies_when: …, expires_at: …}` |
| `AttachDon` | `{target: <filter>, count: N}` |
| `Bounce` | `{target: <filter>}` (return to hand) |
| `AddDon` | `{count: N, state: active\|rested}` |
| `TrashHand` | `{count: N, chooser: controller\|opponent}` |
| `GrantKeyword` | `{target: <filter>, keyword: str, applies_when: …, expires_at: …}` |

### 3.2 Combinators

| Node | Shape |
|---|---|
| `Sequence` | `{steps: [<effect>, …]}` (A then B then C) |
| `If` | `{condition: <cond>, then: <effect>, else?: <effect>}` |
| `Choice` | `{prompt: str, effect: <effect>}` (a "you may" optional effect) |
| `ForEach` | `{filter: <filter>, do: <effect>}` (apply per matching target) |

### 3.3 Conditions (for `If`)

| Condition | Shape |
|---|---|
| `DonCount` | `{op: ge\|eq\|le, value: N}` |
| `LifeCount` | `{op: …, value: N}` |
| `HandCount` | `{op: …, value: N}` |
| `ControllerHas` | `{filter: <filter>, op: ge\|eq, value: N}` |

### 3.4 Filters

A composable target/condition predicate:

```yaml
{
  controller: own | opponent | any,    # default: own
  zone: field | hand | leader | character,  # default: field
  type: Leader | Character | Event,    # optional
  subtype_includes: [Straw Hat Crew, …],  # AND across listed; OR-of-any semantics
  color_includes: [Red, …],
  power_le: 4000, power_ge: 5000,
  cost_le: 3,
  this_card: true                      # self-reference to the source card
}
```

"Your Straw Hat character with 4000 power or less" =
```yaml
{ controller: own, type: Character, subtype_includes: [Straw Hat Crew], power_le: 4000 }
```

The same filter shape works as a KO target, a GivePower target, a ForEach iteration set, and a `ControllerHas` predicate.

## 4. Trigger taxonomy

| Type | Examples | Resolves when | Engine location |
|---|---|---|---|
| **Immediate trigger** | `[On Play]`, `[When Attacking]`, `[On Block]`, `[On K.O.]` | At the moment of the event, before any other action | Pushes onto `effect_stack`, resolver runs to completion (or pause) |
| **Phase-scheduled trigger** | `[End of Your Turn]`, `[At Start of Your Turn]` | At the matching phase boundary | Engine scans field at phase entry, queues, asks player ordering, pushes onto stack |
| **Until-X scoped effect** | "+2000 power until end of battle / turn" | Lazy: applied on every relevant query | Stored in `state.scoped_effects`, consulted by combat / `effective_keywords` / etc. |
| **Static / continuous** | Stage cards, leader auras like "your Straw Hat chars gain +1000 during your turn" | Continuously, applied at query time | Query-time scan of cards-on-field with static-effect entries |
| **Activated** | `[Activate: Main]` abilities | Player declares activation as their main-phase action | New `ActivateAbility` action handler + `effect_stack` |
| **Counter window** | `[Counter]`-keyword triggered effects on counter cards | During `BATTLE_COUNTER`, when the counter card is played | Battle phase machine + `effect_stack` |
| **Life-card trigger** | `[Trigger]` on revealed life card | Player chooses to activate during `BATTLE_TRIGGER` | Existing scaffold + `ActivateTrigger` action handler |

### 4.1 v1 scope (Batch A)

✅ **Implemented in v1:**
- Immediate trigger (`[On Play]`, `[When Attacking]`)
- Until-X scoped effects (the new `ScopedEffect` mechanism — see §6)
- Counter-window triggered effects (extends current static counter values)

⏭ **Deferred to v2 (Batch B):**
- Phase-scheduled triggers
- Activated abilities
- Life-card triggers

⏭ **Deferred to v3 (Batch C):**
- Static/continuous effects (Stage cards) — needs a query-time evaluation pass not yet built

## 5. Resolver model

### 5.1 Re-walk with input log

The resolver is a pure function `resolve(effect_tree, initial_state, inputs_collected) → (new_state, optional_input_request)`. Each "walk" starts from the snapshot of state at the moment the effect first started resolving, applies prior inputs at the choice points it has already passed, and either:

- Reaches the end of the tree → returns final state. Engine pops the entry from `effect_stack`.
- Hits an unanswered choice point → writes `pending_input`, returns. Walk's mutations are discarded.

When `RespondInput` arrives:
1. Engine reads `pending_input.resume_context` to find the `effect_stack` entry that paused.
2. Appends the player's `choices` to that entry's `inputs_collected`.
3. Re-calls resolver. Resolver walks from the same `initial_state`, uses the new input at the next choice point, continues until done or pauses again.

From the player's perspective, each unanswered question is asked exactly once. They never see anything happen twice.

### 5.2 Why re-walk vs freeze-and-resume

Both are functionally equivalent in observable behavior. The implementation cost differs:

- **Freeze-and-resume** would store the resolver's call-stack position (which loop iteration, which `If` branch, which local variables). Painful to serialize for replays.
- **Re-walk** stores only (initial_state_ref, inputs_collected). Replays work for free: feed the answer list back in, get the same outcome.

Initial state snapshots are free in this engine because all states are immutable — just hold a reference.

### 5.3 Updated `StackEntry`

```python
@dataclass(frozen=True)
class StackEntry:
    effect:               dict   # the DSL node tree (root)
    source_instance_id:   str
    controller:           PlayerID
    inputs_collected:     tuple[tuple[str, ...], ...] = ()
    initial_state_ref:    GameState                  # snapshot at push time
```

`initial_state_ref` is a reference, not a deep copy — immutable states make this free. There is a notional cycle (state → stack → entry → state_ref → ...), but it never causes problems because we never traverse `initial_state_ref.effect_stack`. The resolver only reads game data (zones, fields) from the snapshot, never the stack itself. To prevent accidental recursion in equality / hashing, `initial_state_ref` is excluded from `StackEntry.__eq__` and `__hash__` via `field(compare=False, hash=False)`.

`pending_input.resume_context` carries `{"stack_entry_index": int}` to identify which entry is paused.

### 5.4 Multiple triggers from one event

When a single event fires multiple triggers (e.g., two `[End of Your Turn]` effects, two `[On K.O.]` effects from a multi-KO):

- Engine collects the eligible triggers into a queue.
- Asks turn player (or non-turn player, depending on rule) to choose ordering via `pending_input` (`request_type: "OrderTriggers"`).
- Player's response orders them; engine pushes them onto `effect_stack` in that order.
- Resolver processes each, top of stack first.

Rule references: 6-6-1-1-3 (turn player orders multiple `[End of Your Turn]`), 6-6-1-1-4 (non-turn player orders `[End of Your Opponent's Turn]`), 1-3-10 (turn player acts first when both must act simultaneously).

### 5.5 Single-card effects don't pre-stack

OPTCG resolves each card play atomically: play card A → its `[On Play]` fires and fully resolves before card B can be played. Per rule 8-1-3-1-1, auto effects activate at the moment of the activation event. The `pending_input` model enforces this naturally — until input is consumed, only `RespondInput` is legal.

## 6. ScopedEffect — unified scoped game-state modification

Replaces both `TempEffect` (state-level power modifier) and `TempKeyword` (card-level keyword grant) with one mechanism. The temporal scoping is generic; only the modification varies.

### 6.1 Shape

```python
@dataclass(frozen=True)
class ScopedEffect:
    target_instance_id: str
    modification:       dict             # typed dict, e.g.
                                         #  {type: PowerMod, amount: -2000}
                                         #  {type: KeywordGrant, keyword: "Rush"}
                                         #  {type: PreventRefresh}
                                         #  {type: CantAttack}
    applies_when:       str   = "always" # always | your_turn | opponent_turn | during_battle
    expires_at:         str   = "BATTLE_CLEANUP"
    expires_at_turn:    Optional[int] = None  # for turn-relative expirations
```

`GameState` gets `scoped_effects: tuple[ScopedEffect, ...]` (replaces `temp_effects` and removes `CardInstance.temp_keywords`).

### 6.2 Lookup helpers

Each part of the engine that cares about a specific modification has a typed lookup:

- `power_modifiers(state, card_id) -> int` — sum of active `PowerMod` entries
- `granted_keywords(state, card_id) -> frozenset[str]` — active `KeywordGrant` entries
- `is_refresh_blocked(state, card_id) -> bool` — any active `PreventRefresh`?
- `can_attack(state, card_id) -> bool` — no active `CantAttack`?

Each helper applies the same filter chain:
1. Match `target_instance_id`
2. Check `applies_when` against current `state.active_player_id` and `state.battle_context`
3. If active, return / accumulate the modification

Combat reads `power_modifiers` during `_do_damage`. `effective_keywords` reads `granted_keywords`. `_do_refresh` reads `is_refresh_blocked` before un-resting each card.

### 6.3 Cleanup sweeps

Engine sweeps expired entries at phase boundaries:

- `BATTLE_CLEANUP` removes `expires_at == "BATTLE_CLEANUP"` entries.
- `END` removes `expires_at == "END_TURN"` entries belonging to the ending turn.
- For `expires_at_turn`-scoped entries: removed when the matching turn's `END` phase is reached.

Existing engine sweep code at `combat._do_cleanup` and `step._do_end` adapts to filter on the new field names.

### 6.4 v1 implementation scope

The full `ScopedEffect` data model ships in v1, but only `PowerMod` and `KeywordGrant` modification types have implemented helpers. `PreventRefresh`, `CantAttack`, etc. are added in later batches as cards demand them. Additive — won't break v1 YAML.

Migration: `TempEffect` and `TempKeyword` are removed. v1 implementation rewrites the existing combat / temp-effect code paths (currently just `_do_damage`'s `temp_effects` loop and `_do_cleanup`'s sweep) to consult `ScopedEffect` instead. No saved-state migration is needed — vanilla MVP only constructs `TempEffect` instances inside test code, not in production paths.

## 7. YAML organization & card linkage

### 7.1 File layout

```
cards/
  effects/
    ST01/
      ST01-005.yaml       # Jinbe
      ST01-007.yaml       # Nami
      …
    ST02/
      ST02-005.yaml       # Killer
      …
    OP01/
      …
```

One file per card. File name = card_id. Editor-friendly (small files, easy diffs, clear ownership).

### 7.2 YAML schema

```yaml
# cards/effects/ST01/ST01-007.yaml
card_id: ST01-007
dsl_status: parsed              # vanilla | parsed | manual_review
authored_by: claude+human       # claude | human | claude+human (for audit)

triggers:
  - on: OnPlay
    effect:
      type: Draw
      count: 2
```

**YAML-to-code term mapping** (the loader translates user-friendly YAML strings into the engine's internal constants when constructing `ScopedEffect`s):

| YAML `until` value | `ScopedEffect.expires_at` |
|---|---|
| `end_of_battle` | `"BATTLE_CLEANUP"` |
| `end_of_this_turn` | `"END_TURN"` (no `expires_at_turn`) |
| `end_of_opponent_turn` | `"END_TURN"`, `expires_at_turn = current + 1` (or +2, depending on phase of creation) |
| `end_of_your_next_turn` | `"END_TURN"`, `expires_at_turn = current + 2` |

Loader rejects unknown `until` values to prevent silent typos.

`dsl_status: vanilla` is for cards with no triggered effects (the deck loader treats them as no-op). `manual_review` is for cards we couldn't author cleanly — engine refuses to load decks that contain them.

### 7.3 Card DB integration

`CardDB.get(card_id)` loads the YAML alongside the existing card definition. The `triggers` field on `CardDefinition` (currently `[]`) is populated from the YAML.

`load_official_deck` validates: every non-vanilla card must have a `parsed` YAML or deck-load fails with a clear error listing missing cards.

### 7.4 LLM-assisted authoring workflow

For Batches B and C:
1. Compose a few-shot prompt: 5–10 hand-authored YAML files from Batch A as examples + the new card's `effect_text` + a short DSL primitive cheat sheet.
2. Send to Claude (or another LLM), get back a draft YAML.
3. Human reviewer compares draft against card text, edits as needed, sets `authored_by: claude+human`.
4. Reviewer runs the loader to validate against the schema.
5. Reviewer runs a smoke game with a deck containing the card to surface obvious resolver failures.
6. Cards Claude couldn't confidently author (low confidence, novel pattern) get `dsl_status: manual_review`.

This is purely an authoring-time tool. Once the YAML is committed, the runtime engine has no LLM dependency; everything stays deterministic and replay-clean.

## 8. Testing strategy

### 8.1 Per-effect unit tests

For each operator and combinator in §3:
- Resolver produces expected state mutations on a synthetic state
- Filter targeting selects the correct cards
- `If` evaluates conditions correctly
- `Choice` writes correct `pending_input` for "you may"
- `ForEach` iterates over the filter's matches

### 8.2 Per-card scenario tests

For each authored card:
- Construct a state where the card's trigger is poised to fire
- Step through the trigger, providing player inputs as needed
- Assert the final state matches expectation

These are the regression net for resolver bugs that affect specific cards.

### 8.3 Resolver re-walk determinism

Property test: for any (initial_state, effect_tree, inputs), repeatedly calling `resolve(...)` with the same inputs returns identical states. Catches accidental state mutation in walk logic.

### 8.4 Replay round-trip

Extend the existing replay test: a game with cards that have authored effects can be saved and replayed to byte-identical end state. The pending_input/RespondInput sequence is captured in the trace; replay just feeds it back.

### 8.5 Loader rejection

Negative tests: deck containing a card with `dsl_status: pending` or `manual_review` must fail to load with a clear error.

## 9. Out of scope (explicitly deferred)

- **Text-to-YAML auto-parser.** The original `EFFECT_TEXT_PARSER.md` plan. May or may not be revisited; LLM-assisted authoring may make it unnecessary.
- **Static / continuous effects** (Stage cards). v3 (Batch C).
- **Phase-scheduled, activated, life-card triggers.** v2 (Batch B).
- **Replacement effects** ("instead of") — rule 8-1-3-4. Rare in starters; deferred until a card needs them.
- **Permanent effects** (rule 8-1-3-3) beyond what `ScopedEffect` covers.
- **Multi-turn / multi-game state.** Effects whose duration crosses game boundaries (none exist in OPTCG).

## 10. Risks & open questions

- **DSL design drift across batches.** Mitigation: strict additive-only rule between batches, captured in `docs/dsl/CHANGELOG.md`. Breaking changes require renaming the operator.
- **LLM hallucinated YAML.** Mitigation: human review on every output, `authored_by` field for audit, smoke game per card.
- **Resolver complexity from `Choice` + `ForEach` interaction.** A `ForEach` that contains a `Choice` produces N input prompts, one per iteration. The re-walk model handles this correctly (each iteration's choice is a separate index in `inputs_collected`), but it's worth a dedicated test.
- **Trigger ordering across simultaneous events.** v1 only has `[On Play]` and `[When Attacking]`, neither of which produces simultaneous triggers in starter decks. v2 will need the multi-trigger ordering machinery from §5.4.

## 11. Acceptance criteria for v1

- 5–10 hand-authored YAML files for ST01–02 cards.
- Resolver implemented for all v1 operators (§3.1) and combinators (§3.2).
- `ScopedEffect` shipped, with `PowerMod` and `KeywordGrant` helpers.
- `CardDB` loads YAML; deck-load rejects unauthored non-vanilla cards.
- Per-card scenario test passing for each authored card.
- Replay round-trip test passing for a game using authored cards.
- Existing 188 engine tests still pass (no regressions).
- `docs/dsl/CHANGELOG.md` exists with v1 entry.
