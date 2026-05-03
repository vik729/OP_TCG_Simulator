# DSL Changelog

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
- `SourceAttachedDon {op, value}` — checks `attached_don` on the effect's source card

### Filters
`controller`, `zone`, `type` (str or list-of-str), `subtype_includes`, `color_includes`, `power_le`, `power_ge`, `cost_le`, `rested`, `this_card`, `not_this_card`

### Triggers wired
- `OnPlay` — fires from `step._handle_play_card` after card moves to field
- `WhenAttacking` — fires from `combat.begin_attack` after attacker rests
- `Counter` — fires from `combat.handle_counter` (defender as controller)

### Resolver
- Re-walk model: `resolve(effect_tree, initial_state, inputs_collected) → (new_state, optional_input_request)`
- `StackEntry` carries `inputs_collected` (log of past `RespondInput.choices`) and `initial_state_ref` (snapshot at push time)
- `RespondInput` in non-SETUP phase appends to top entry's `inputs_collected` and re-resolves
- Auto-skip empty target choices when `min_choices=0` (no infinite "choose nothing" stall)

### ScopedEffect
- Replaces `TempEffect` and `TempKeyword`
- Two axes: `applies_when` (`always` | `your_turn` | `opponent_turn` | `during_battle`) and `expires_at` (`BATTLE_CLEANUP` | `END_TURN`) plus optional `expires_at_turn`
- v1 supports two modification types: `PowerMod` and `KeywordGrant`
- Lookups: `power_modifiers(state, id)` (wired into combat), `granted_keywords(state, id)` (wired into `effective_keywords`)

### Cards authored (5)
- `ST01-006` Tony Tony Chopper — vanilla baseline (Blocker keyword only)
- `ST01-005` Jinbe — `[DON!! x1] [When Attacking]` +1000 to ally for the turn
- `ST01-011` Brook — `[On Play]` give up to 2 rested DON to a Leader/Character
- `ST01-014` Guard Point — `[Counter]` +3000 to a Leader/Character this battle (life-card `[Trigger]` half deferred to v2)
- `ST02-005` Killer — `[On Play]` KO opponent rested Character cost ≤ 3

### `until` value mappings
| YAML | `expires_at` | `expires_at_turn` |
|---|---|---|
| `end_of_battle` | `BATTLE_CLEANUP` | `None` |
| `end_of_this_turn` | `END_TURN` | `None` |
| `end_of_opponent_turn` | `END_TURN` | `current_turn + 1` |
| `end_of_your_next_turn` | `END_TURN` | `current_turn + 2` |

### Deck-load gating
`validate_deck` rejects cards with `dsl_status` outside `{vanilla, parsed, pending}`. Pending cards play as vanilla in v1 — their effects don't fire because `triggers=()`. Tightening to `{vanilla, parsed}` happens once all starter cards have authored YAML.

### Deferred to v2 (Batch B — full ST01-04)
- Phase-scheduled triggers (`EndOfYourTurn`, `AtStartOfYourTurn`)
- Activated abilities (`ActivateMain`)
- Life-card triggers (`Trigger` keyword on revealed life cards)
- The `[Trigger]` half of `ST01-014` Guard Point
- Authoring YAMLs for the remaining ST-01..ST-04 cards

### Deferred to v3 (Batch C — boosters)
- Static / continuous effects (Stage cards, leader auras like "Your Straw Hat chars gain +1000 during your turn")
- `PreventRefresh`, `CantAttack`, and other `ScopedEffect.modification` types beyond `PowerMod` and `KeywordGrant`
