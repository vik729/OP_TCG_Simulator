# DSL Changelog

## v2 (2026-05-03) — event-driven mechanics

10 new mechanics on top of v1. All variations of "trigger fires → resolver runs → state mutates" — no new evaluation pass. Continuous effects (Stage cards, leader auras) deferred to v3.

### New trigger types
- `EndOfYourTurn` — fires at END phase, in current turn player's context (rule 6-6-1-1)
- `AtStartOfYourTurn` — fires at REFRESH phase, after un-resting and before DRAW
- `ActivateMain` — player-initiated during MAIN phase via `ActivateAbility(card_instance_id, trigger_index)`
- `Trigger` — life-card revealed on leader damage; defender chooses `ActivateTrigger` or `PassTrigger`. Banish keyword on attacker still skips.

### Cost array (for ActivateMain)
- `RestSelf` — rest the source card; fails if already rested
- `RestDon {amount: N}` — rest N active DON; fails if not enough
- Costs paid atomically; first failure aborts activation with no state change.

### `once_per_turn` field on triggers
Cleared during REFRESH phase via existing `PlayerState.once_per_turn_used` set.

### Activated ability flow (`engine/step.py::_handle_activate_ability`)
Resolves trigger by index, enforces OPT, pays cost array, marks OPT used, pushes effect onto `effect_stack`. `engine/legal_actions.py` enumerates available activations and pre-checks cost feasibility.

### Life-card trigger flow (`engine/combat.py`)
`_apply_leader_damage` detects `Trigger` on revealed life card and pauses in `BATTLE_TRIGGER` phase (unless attacker has Banish). `BattleContext.pending_trigger_damage` carries remaining damage across the pause. Card destination on activate dictated by type:
- Character → Field (OnPlay triggers also fire)
- Event → Trash (effect resolves first)
- Stage → Hand (Stage handling deferred to v3)

### New `ScopedEffect.modification` types + lookups
- `CostReduction {amount: -N}` — `cost_reduction_for(state, controller, cdef)` consulted in `_handle_play_card`. Effective cost clamped to 0.
- `CantAttack` — `can_attack(state, instance_id)` consulted in `legal_actions`. Filters out DeclareAttack options.
- `PreventRefresh` — `is_refresh_blocked(state, instance_id)` consulted in `_do_refresh`. Card stays rested through the phase; attached DON still returns per rule 6-2-3.

### New operators (`engine/dsl/operators.py`)
- `SearchDeck {count: N, filter: <filter>, add_to_hand_max: M, remainder: bottom_of_deck|trash}` — reveal top N, filter eligible, player picks up to M, remainder goes to bottom or trash
- `SearchTrash {filter: <filter>, add_to_hand_max: M}` — pick from filtered trash, move chosen to hand
- `Rest {target: <filter>, max_choices: N}` — force-rest target cards (no-op on already-rested)

### Filter zone map extended
`zone: deck`, `zone: trash`, `zone: life` now resolvable (used by SearchDeck / SearchTrash internals).

### Event-card play-and-trash fix (engine bug)
`_handle_play_card` now branches on `cdef.type`: Events go to Trash after their `OnPlay` effect resolves; Characters / Stages still go to Field. Fixes a v1 bug where Events were left on the field.

### Loader extensions
- `ALLOWED_TRIGGERS` adds `Trigger`
- `ALLOWED_COST_TYPES = {RestSelf, RestDon}`
- Trigger schema now normalizes to `{on, effect, cost, once_per_turn}`

### Viewer extensions (`engine/play.py`)
Formats `ActivateAbility#N`, `ActivateTrigger`, `PassTrigger`.

### Cards authored
- `ST02-007` Jewelry Bonney — `[Activate: Main] (1) (rest self): Look at top 5, reveal up to 1 Supernovas, add to hand. Remainder bottom of deck.` Validates ActivateMain + RestDon + RestSelf + SearchDeck end-to-end.

### Tests
- 271 tests passing (was 241 in v1; +30 v2 tests)
- New test files: `test_v2_phase_scheduled.py`, `test_v2_activated.py`, `test_v2_life_trigger.py`, `test_v2_cost_reduction.py`, `test_v2_cant_attack.py`, `test_v2_prevent_refresh.py`, `test_v2_search.py`, `test_v2_event_card.py`, `test_v2_card_scenarios.py`, `test_trigger_queue.py`
- `test_zone_deltas.py` envelope widened for v2 actions

### Deferred
- **Static / continuous effects** (v3): Stage cards, leader auras, "Your characters gain X" passives.
- **OPT per-trigger granularity** (one OPT per card_id is sufficient for v2).
- **"In any order" SearchDeck remainder** (player-chosen ordering of leftover cards).
- **CostReduction `target_filter`** (narrows applicability to specific card types).
- **Mass card authoring** (LLM-assisted) for ST03-ST29 / OP-XX / EB-XX.

## v1 (2026-05-02) — Batch A

First runnable DSL: hand-authored YAML for 5 ST-01/ST-02 cards, resolver, ScopedEffect mechanism, YAML loader.

### Operators
- `Draw {count: N}`
- `KO {target: <filter>, max_choices: N}`
- `Bounce {target: <filter>, max_choices: N}` (return to hand)
- `AddDon {count: N, state: active|rested}`
- `AttachDon {target: <filter>, count: N, state: active|rested, max_choices: N}`
- `TrashHand {count: N, chooser: controller|opponent}`
- `GivePower {target: <filter>, amount: ±N, until: <until>, max_choices: N, applies_when?: <pred>}`
- `GrantKeyword {target: <filter>, keyword: str, until: <until>, max_choices: N, applies_when?: <pred>}`

### Combinators
- `Sequence {steps: [...]}`
- `If {condition: <cond>, then: <effect>, else?: <effect>}`
- `Choice {prompt: str, effect: <effect>}` (yes/no "you may")
- `ForEach {filter: <filter>, do: <effect>}`

### Conditions
- `DonCount {op, value}`
- `LifeCount {op, value}`
- `HandCount {op, value}`
- `ControllerHas {filter, op, value}`
- `SourceAttachedDon {op, value}`

### Filters
`controller`, `zone`, `type` (str or list-of-str), `subtype_includes`, `color_includes`, `power_le`, `power_ge`, `cost_le`, `rested`, `this_card`, `not_this_card`

### Triggers wired
`OnPlay` (PlayCard), `WhenAttacking` (DeclareAttack), `Counter` (PlayCounter)

### Resolver
Re-walk model with `inputs_collected` log on `StackEntry` and `initial_state_ref` snapshot.

### ScopedEffect
Replaces TempEffect/TempKeyword. Two axes: `applies_when` (`always` | `your_turn` | `opponent_turn` | `during_battle`), `expires_at` (`BATTLE_CLEANUP` | `END_TURN`) plus `expires_at_turn`. v1 modifications: `PowerMod`, `KeywordGrant`.

### Cards authored
- `ST01-006` Tony Tony Chopper (vanilla baseline, Blocker)
- `ST01-005` Jinbe — `[DON!! x1] [When Attacking]` +1000 to ally for the turn
- `ST01-011` Brook — `[On Play]` give up to 2 rested DON
- `ST01-014` Guard Point — `[Counter]` +3000 this battle
- `ST02-005` Killer — `[On Play]` KO opponent rested cost ≤ 3
