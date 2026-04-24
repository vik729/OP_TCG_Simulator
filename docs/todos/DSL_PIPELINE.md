# TODO: DSL Pipeline — Phase 3

> **Status**: Deferred. Complete Phase 1 (fetch) and Phase 2 (normalize) first.
> After normalization, audit all unique `effect_text` patterns across ST01–ST04
> before designing the parser.

---

## Goal

Convert the raw `effect_text` string on each card into the structured `triggers[]`
DSL array defined in `docs/ARCHITECTURE.md`, changing each card's `dsl_status`
from `"pending"` to `"parsed"` (or `"manual_review"` for edge cases).

---

## Prerequisite: Audit Effect Text Patterns

Before writing a single line of parser code, run an audit of all unique effect
text patterns across the normalized card set. This tells you:

- How many distinct trigger types exist
- Which effect patterns are most common (prioritize those first)
- Which cards have unique/complex effects that need manual DSL authoring

### Suggested audit script: `tools/audit_effects.py`

Should output:
1. A frequency table of trigger keywords (`[On Play]`, `[When Attacking]`, etc.)
2. A grouped list of all unique `effect_text` values by trigger type
3. A count of cards with no effect text (vanilla cards)
4. Cards whose text includes `"you may"`, `"choose"`, `"opponent"` — these are
   likely to need `Choice` or `Conditional` DSL combinators

---

## Phase 3 Design (when ready)

### Parser approach
A **pattern-matching parser**: regex rules map common effect text templates
to DSL nodes. Cards that don't match any pattern are flagged as `"manual_review"`.

### Effect primitives to implement first (most common in starter decks)
| Effect text pattern | DSL op |
|---------------------|--------|
| `Draw N card(s)` | `Draw` |
| `Give +N power to one of your Characters` | `GivePower` |
| `KO up to N of your opponent's Characters with a cost of N or less` | `KO` |
| `Add N DON!! card(s) from your DON!! deck` | `AddToDon` |
| `Return this card to its owner's hand` | `Bounce` |
| `[Your Turn] All of your Characters gain +N power` | `GivePower` (static) |
| `Search your deck for N card(s) with ...` | `Search` |
| `Trash the top N card(s) of your deck` | `Trash` |

### Trigger type mapping
| Text token | DSL `trigger_type` |
|------------|-------------------|
| `[On Play]` | `OnPlay` |
| `[When Attacking]` | `WhenAttacking` |
| `[On K.O.]` | `OnKO` |
| `[End of Your Turn]` | `EndOfTurn` |
| `[Start of Your Turn]` | `StartOfTurn` |
| `[Counter]` | `OnCounter` |
| `[Activate: Main]` | `ActivateMain` |
| `[DON!! xN] [Your Turn]` | `StaticWhileActive` |

### Output scripts
- `tools/parse_dsl.py` — runs the parser, updates `triggers[]` and `dsl_status`
- `tools/audit_effects.py` — reports unparsed cards for manual review

---

## Acceptance criteria for Phase 3

- [ ] `dsl_status: "parsed"` on ≥ 80% of ST01–ST04 cards
- [ ] All vanilla cards (no effect text) marked `dsl_status: "parsed"` with `triggers: []`
- [ ] All `"manual_review"` cards listed in a report with their `effect_text`
- [ ] At least one full game-playable deck (ST01) has 100% DSL coverage
