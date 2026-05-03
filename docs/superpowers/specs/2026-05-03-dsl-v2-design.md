# OP TCG DSL v2 Design

> **Status:** Brainstormed 2026-05-03. Awaiting plan.
> **Predecessor:** `2026-05-02-dsl-design.md` (DSL v1 / Batch A, complete; tagged `v0.2-dsl-v1`)
> **Deferred to v3:** Static / continuous effects (Stage cards, leader auras) — fundamentally different evaluation model (query-time scan), warrants its own design.

## 1. Goal

Add the event-driven mechanics that v1's deferred list and the broader card corpus demand, so the engine can run cards from ST-03..ST-29 and OP-01..OP-13 (mass authoring is a follow-on, not part of this spec).

v1 covers: `OnPlay`, `WhenAttacking`, `Counter` triggers; PowerMod / KeywordGrant scoped effects; Draw, KO, Bounce, AddDon, AttachDon, TrashHand, GivePower, GrantKeyword operators; Sequence / If / Choice / ForEach combinators.

v2 adds 10 mechanics on top, all variations of "trigger fires → resolver runs → state mutates." None require a new evaluation pass — they extend existing engine patterns.

## 2. Mechanics

### 2.1 Trigger types (3)

#### `EndOfYourTurn`, `AtStartOfYourTurn` — phase-scheduled

When a phase is entered, scan all cards on the field for matching triggers. If 0, no-op. If 1, push directly onto `effect_stack`. If >1, write `pending_input` asking the turn player to order them, then push in chosen order.

- `END` phase scans for `EndOfYourTurn` *before* its turn-flip / scoped-effect-sweep logic, so triggers resolve in the ending player's turn context (rule 6-6-1-1).
- `REFRESH` phase scans for `AtStartOfYourTurn` *after* its un-resting logic but before passing to `DRAW` (rule 6-2).

Helper module `engine/dsl/trigger_queue.py`:
- `find_triggers_for_event(state, event_type, db) -> list[(card, trigger)]`
- `queue_for_ordering(state, triggers, controller) -> state` — handles 0/1/many cases. For >1, sets `pending_input` with `request_type: "OrderTriggers"`, `valid_choices: tuple of trigger_index strings ("0", "1", "2", ...)`, `min_choices=max_choices=len(triggers)`. Player's response is the order; engine pushes onto stack accordingly.

Resolver re-walk handles per-trigger resolution unchanged.

#### `ActivateMain` — activated abilities

`ActivateAbility(card_instance_id, trigger_index)` action becomes legal during MAIN phase when:
- The card is on field
- It has at least one `ActivateMain` trigger at `trigger_index`
- For OPT-marked abilities: `card.instance_id` is not in `state.active_player().once_per_turn_used`
- All activation costs are payable

YAML schema:
```yaml
- on: ActivateMain
  once_per_turn: true
  cost:
    - { type: RestSelf }            # rest the source card
    - { type: RestDon, amount: 1 }  # rest N active DON
  effect: { type: Draw, count: 1 }
```

Handler attempts to pay each cost atomically. If any cost fails (e.g., not enough active DON), abort with no state change. On success, mark OPT used and push `effect` onto `effect_stack`.

`PlayerState.once_per_turn_used` already exists; v2 populates it. Cleared in REFRESH (already wired).

For v2 simplicity: only one OPT ability per card_id (key on `card.instance_id`). If a card has multiple ActivateMain triggers, only one is OPT-tracked across them. Refinement deferred.

Cost operators (NEW, used only inside the `cost` array):
- `{type: RestSelf}` — rest the source card; fails if already rested
- `{type: RestDon, amount: N}` — rest N active DON; fails if not enough active

#### `Trigger` — life-card triggers

Wires the existing `Phase.BATTLE_TRIGGER` scaffold and `ActivateTrigger` / `PassTrigger` actions.

Flow inside `_apply_leader_damage`:
1. Reveal top life card (already happens; card moves to hand by default).
2. **Decision point:** if revealed card has a `Trigger` event in its YAML AND the attacker does NOT have the `Banish` keyword (rule 4-6-3-1: Banish prevents Triggers because the card cannot reach hand): pause the damage application; set `phase = BATTLE_TRIGGER`; await `ActivateTrigger` or `PassTrigger`.
3. **`PassTrigger`:** card moves to hand (default behavior). Resume `_apply_leader_damage` for any remaining damage (Double Attack).
4. **`ActivateTrigger`:** the engine "plays the card for free" (cost bypassed) and runs its trigger effect. Card destination is dictated by its `type`:
   - **Character**: → Field (and any `OnPlay` triggers on the card fire normally via the existing OnPlay path)
   - **Event**: trigger effect resolves, then card → Trash (Events trash after activation per rule 2-7-3 spirit)
   - **Stage**: → Stage area (deferred to v3 with Stage card support; rejected at deck-load until then)
5. After Trigger resolution, resume `_apply_leader_damage` for any remaining damage.

Banish keyword: revealed life card → trash, no Trigger fires. Already implemented in v1 for the damage path; v2 adds the "no Trigger" gate.

### 2.2 ScopedEffect modifications (3)

Each adds a typed dict, a lookup helper in `engine/dsl/lookups.py`, and one engine query point. ~30 lines per mechanic. Follows the existing `PowerMod` / `KeywordGrant` pattern from v1.

#### `CostReduction`

```python
{"type": "CostReduction", "amount": -N, "target_filter": <filter or None>}
```

- Lookup: `cost_reduction_for(state, card_def, controller) -> int` — sums all active CostReduction modifications whose `target_filter` matches `card_def`. Returns a non-positive integer (so caller adds it to base cost; result is clamped to 0 minimum).
- Hook: `_handle_play_card` in `engine/step.py` — effective cost = `max(0, cdef.cost + reduction)` consulted before checking active DON.
- `target_filter` semantics: if absent, applies to all the controller's plays. If present, must match the card being played's definition (filter against `cdef`, not a CardInstance — so subtype/type/color filters work). Reuses existing filter language but operates on `CardDefinition` (a small adapter wraps `cdef` so it looks like a CardInstance to `matches`).
- Duration: typically `expires_at: END_TURN`. v2 does not implement "next play only" semantics (would require consuming the effect on use); deferred.

#### `CantAttack`

```python
{"type": "CantAttack"}
```

- Lookup: `can_attack(state, card_id) -> bool` — False if any active CantAttack ScopedEffect targets `card_id`.
- Hook: `legal_actions._legal_main_actions` — skip generating `DeclareAttack` options for any attacker where `can_attack` returns False.

#### `PreventRefresh`

```python
{"type": "PreventRefresh"}
```

- Lookup: `is_refresh_blocked(state, card_id) -> bool`
- Hook: `_do_refresh` in `engine/step.py` — for each card-on-field, check before un-resting; skip if blocked. Same for attached DON: don is returned to cost area BUT not refreshed if the card it was attached to was prevented from refreshing? Re-read rule 6-2-3: "Return all DON!! cards given to cards in your Leader area and Character area to your cost area and rest them." So even on prevented-refresh, attached DON returns. The PreventRefresh modification only affects the card's `rested` flag.

### 2.3 Operators (3 + cost-helpers)

#### `SearchDeck`

```yaml
type: SearchDeck
count: 5                                      # reveal top N
filter: { subtype_includes: [Supernovas] }    # narrow (optional; default = match-anything)
add_to_hand_max: 1                            # max cards player adds to hand
remainder: bottom_of_deck                     # or: trash
```

Flow (inside the resolver re-walk):
1. Take the top `count` cards from the controller's deck (a transient list `revealed`).
2. Filter against `filter` to produce `eligible` (subset of `revealed`).
3. If `add_to_hand_max == 0` or `eligible` is empty → skip the choice; jump to step 5.
4. Otherwise pause for `pending_input(request_type="ChooseCards", valid_choices=tuple of eligible.instance_id, min_choices=0, max_choices=add_to_hand_max)`. On RespondInput, move chosen cards from deck to hand.
5. **Remainder handling** — the `count - len(chosen)` un-chosen cards (still revealed):
   - `remainder: bottom_of_deck` — moved to bottom of deck in their revealed order (no further player choice)
   - `remainder: trash` — moved to controller's trash (face-up, in revealed order)

Determinism note: `revealed` is just `deck[:count]`. Re-walking this operator in a replay produces identical `revealed` and `eligible` lists. The player's `chosen` is captured in `inputs_collected`. No new randomness introduced.

#### `SearchTrash`

```yaml
type: SearchTrash
filter: { type: Character }
add_to_hand_max: 1
```

Flow: filter trash, ask player for `add_to_hand_max` choices via `pending_input`, move chosen to hand. No remainder concept (un-chosen cards stay in trash).

#### `Rest`

```yaml
type: Rest
target: { controller: opponent, type: Character }
max_choices: 1
```

Pick targets, set `rested=True`. Rejects targets that are already rested (filter would need to add `rested: false` for cleanliness; or the operator silently no-ops on already-rested). v2 silently no-ops to keep the operator simple.

#### Cost-helper operators (used only in `cost` arrays)

`RestSelf` and `RestDon` (defined in §2.1 ActivateMain). Each `apply_X` returns `(state, None, choice_index)` on success, or raises `ActivationCostFailed` on failure (caught by the `ActivateAbility` handler to abort the activation).

### 2.4 Event-card play-and-trash fix (engine bug, v1 leftover)

Currently `_handle_play_card` always moves the card to Field regardless of `cdef.type`. For Event cards this is wrong — Events should:
1. Pay cost (already correct)
2. Run the card's `OnPlay` trigger effect (already correct)
3. Card → Trash (NOT Field)

Fix: in `_handle_play_card`, branch on `cdef.type`:
- `Character` / `Stage`: existing behavior (→ Field)
- `Event`: skip the field-add; instead append to controller's trash. (After the OnPlay effect resolves; same ordering as today.)

The Event being trashed AFTER OnPlay matters because some effects reference "the source card" — needs the card to still notionally be the source during effect resolution. Implementation: bind `source_instance_id` on the StackEntry to the card's instance_id (existing behavior); the card moves to trash after the resolver finishes that entry. For v2, simplest: do the trash move in `_handle_play_card` *after* pushing the StackEntry but the card data on the StackEntry still references the played-card instance. Resolver looks up the card via `get_card`, which finds it in trash — same data. Works.

## 3. Architecture changes

### 3.1 New / modified files

**New:**
- `engine/dsl/trigger_queue.py` — find/order/queue helpers for phase-scheduled and life-card triggers
- `engine/dsl/cost_helpers.py` — `RestSelf`, `RestDon` operators with `ActivationCostFailed` exception

**Modified:**
- `engine/game_state.py` — no field changes (StackEntry shape is sufficient)
- `engine/step.py` — extend `_handle_play_card` (Event-card fix, CostReduction lookup), `_handle_advance_phase` (END / REFRESH trigger scans), `_do_refresh` (PreventRefresh lookup), implement `_handle_activate_ability` (currently raises NotImplementedError)
- `engine/combat.py` — extend `_apply_leader_damage` (life-card Trigger gate), wire new BATTLE_TRIGGER phase actions
- `engine/dsl/lookups.py` — add `cost_reduction_for`, `can_attack`, `is_refresh_blocked`, `is_trigger_suppressed` helpers
- `engine/dsl/operators.py` — add `SearchDeck`, `SearchTrash`, `Rest` to `_OPERATORS`
- `engine/dsl/loader.py` — extend `ALLOWED_TRIGGERS` to include `EndOfYourTurn`, `AtStartOfYourTurn`, `ActivateMain`, `Trigger`; add cost-array validation; add `once_per_turn` field
- `engine/legal_actions.py` — extend `_legal_main_actions` to enumerate ActivateAbility for cards with `ActivateMain` triggers; consult `can_attack`
- `engine/phase_machine.py` — add `ActivateAbility` to MAIN's legal actions; wire `ActivateTrigger`/`PassTrigger` for BATTLE_TRIGGER
- `engine/play.py` — verbose viewer learns to print Activate/Trigger actions readably (small)

### 3.2 No changes to

- `ScopedEffect` shape (modification field is open, just adding new types)
- Resolver re-walk model
- `pending_input` / `RespondInput` mechanics
- File layout for YAML (`cards/effects/<set>/<id>.yaml`)
- `dsl_status` gating

## 4. Authoring plan (after implementation)

v2 implementation **does not require** mass card authoring. The implementation tasks include 5–8 hand-authored cards from across ST-03..ST-29 to validate each new mechanic end-to-end. Mass authoring (LLM-assisted) becomes a separate effort once mechanics are stable.

Suggested validation cards (one per mechanic, small overlap):
- `EndOfYourTurn`: ST-04 (Kaido) has ones — pick a representative
- `AtStartOfYourTurn`: pick from corpus
- `ActivateMain` (no OPT): ST01-007 Nami `[Activate: Main] [Once Per Turn] Give up to 1 rested DON to your Leader or Character`
- `ActivateMain` (with OPT): Nami again (same card, two test cases)
- `Trigger` (Character with PlayThis-style): pick a Character with `[Trigger] Play this card`
- `Trigger` (Event): pick an Event with a substantive trigger effect
- `CostReduction`: pick from corpus
- `CantAttack`: pick from corpus (or hand-author a synthetic test card)
- `PreventRefresh`: synthetic test card; rare in ST-01..ST-04
- `SearchDeck` (bottom_of_deck): ST02-007 Jewelry Bonney `[Activate: Main] (1): Look at 5, reveal up to 1 Supernovas, add to hand. Then place rest at bottom in any order.`
- `SearchDeck` (trash): pick from corpus
- `SearchTrash`: pick from corpus
- `Rest`: ST01-016 Diable Jambe-style or simpler "rest opponent's character"
- `Event-card play`: ST01-014 Guard Point already has `[Counter]` (which is event-counter); needs an `[On Play]` Event for full coverage — pick from corpus (e.g., a "Trash 1, draw 1" event)

Card pick is *suggestive*, not required — the implementer can substitute cards that better exercise the mechanic.

## 5. Testing

- Per-mechanic unit tests in `tests/dsl/test_v2_*.py`:
  - `test_v2_phase_scheduled.py` — multiple EndOfYourTurn triggers, ordering, single trigger short-circuit
  - `test_v2_activated.py` — ActivateMain with cost (success + failure), OPT enforcement, OPT cleared on REFRESH
  - `test_v2_life_trigger.py` — pass branch, activate Character branch, activate Event branch, Banish blocks Trigger
  - `test_v2_cost_reduction.py` — modification applies, clamped to 0, target_filter narrows
  - `test_v2_cant_attack.py` — DeclareAttack absent from legal_actions when CantAttack present
  - `test_v2_prevent_refresh.py` — card stays rested through refresh
  - `test_v2_search.py` — SearchDeck (bottom + trash variants), SearchTrash, with and without filter matches
  - `test_v2_rest.py` — Rest applies to chosen target
- Per-card scenario tests in `tests/dsl/test_card_scenarios.py` (extend existing): 1 test per validation card.
- Replay round-trip test extension: ensure a game using v2 mechanics replays identically.
- Existing 241 tests must continue to pass (no regressions).

## 6. Out of scope (deferred)

- **Static / continuous effects** (v3): Stage cards, leader auras, "Your characters gain X power" passive effects.
- **"Next play only" cost reduction semantics** (v3 or later): consuming-on-use cost reduction.
- **OPT per-trigger granularity**: v2 uses one OPT per card; multiple OPT abilities on one card (unusual) deferred.
- **"In any order" remainder for SearchDeck**: the v2 `bottom_of_deck` remainder uses revealed order; player-chosen order deferred.
- **Replacement effects** ("instead of X, do Y") — rule 8-1-3-4. Rare; deferred.
- **Mass card authoring** (LLM-assisted) — separate effort after v2 is stable.

## 7. Risks & open questions

- **Trigger ordering UX**: Pre-order via one InputRequest is clean for non-cascading triggers (most cases). If a v2 card later triggers another mid-resolution, the new trigger gets pushed onto the stack and resolves before continuing the queue — this is correct OPTCG behavior (newest auto effects resolve first when they fire mid-resolution). No design change needed; just be aware during testing.
- **Event-card `_handle_play_card` fix** could break existing v1 tests that use Events. Need to audit `tests/test_step.py::test_full_setup_to_main` and the random-game tests for any reliance on the buggy behavior.
- **Activated abilities + `legal_actions`**: enumerating all `ActivateAbility(card_id, trigger_index)` options for every field card every turn could grow combinatorially in future sets. For v2's small authored set this is fine; future optimization (lazy enumeration) deferred.

## 8. Acceptance criteria for v2

- All 3 trigger types implemented and exercised by at least one authored card each
- All 3 ScopedEffect modifications implemented with lookups wired into the right engine query points
- All 4 operators (SearchDeck × 2 variants, SearchTrash, Rest) implemented and tested
- Cost helpers (RestSelf, RestDon) implemented and used by the activated-ability test card
- Event-card play-and-trash fix shipped; existing tests still green
- 5–8 hand-authored cards covering each new mechanic
- 241 v1 tests + new v2 tests all pass
- `docs/dsl/CHANGELOG.md` v2 entry committed
- Tag `v0.3-dsl-v2` (local; user pushes separately)
