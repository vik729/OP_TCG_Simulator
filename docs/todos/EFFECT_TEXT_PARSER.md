# TODO: Effect Text Parser (DSL phase)

> **Status**: Deferred. Vanilla MVP has no triggered effects. Triggered
> effects need a DSL parser. This is the central problem of the DSL phase.
> Subsumes `SMART_KEYWORD_REGEX.md`.

## Goal

Convert the raw `effect_text` string on each card into the structured `triggers[]`
DSL array defined in `docs/ARCHITECTURE.md`, changing each card's `dsl_status`
from `"pending"` to `"parsed"` (or `"manual_review"` for edge cases).

## Why this is the central problem

Effect text is hard not because the meanings are complex, but because:

1. **Multiple bracket notations** (rules §2 disambiguation):
   - `{Type}` → references a subtype
   - `<Attribute>` → references an attribute
   - `[Card Name]` → references a card by name
   - `[Keyword]` → references a keyword (same notation as card name!)
   - `[On Play]` etc. → trigger markers
   - `[DON!! xN]` → cost / condition
2. **Conditional structures** (`[Your Turn]`, `[DON!! xN]`, `[Once Per Turn]`)
3. **Choice clauses** (`up to N`, `you may`, `if ...`)
4. **Filter sub-language** (e.g. "your {Straw Hat Crew} Characters")
5. **Effect verbs** (Draw, KO, GivePower, AddDon, etc. — see EFFECT_MAP.md)

Each of these needs structured representation in the DSL dict that goes onto
`StackEntry.effect`.

## Approach (when picked up)

1. **Read existing `docs/EFFECT_MAP.md`** — it already audits the patterns
   in ST01–04 and identifies candidate DSL primitives.
2. **Design the filter sub-schema** first — every effect needs to express
   "which cards does this affect?" via a structured filter (subtype_includes,
   attribute_is, color_includes, name_contains, cost_le, power_le, etc.).
3. **Implement effect verbs** in priority order from `EFFECT_MAP.md` (most
   frequent first): GivePower (10x), SetActive (9x), KO (7x), Bounce (5x),
   Draw (5x), TrashHand (4x), AddDon (4x), AttachDon (3x).
4. **Implement combinators**: Sequence, Choice, Conditional, ForEach, Optional.
5. **Implement the parser** as a series of pattern matchers:
   - Match the trigger marker (`[On Play]`, `[When Attacking]`, etc.) →
     determines the trigger type.
   - Match the effect verb → maps to a DSL op.
   - Match the target/filter clause → produces the filter sub-dict.
   - Combine into a structured trigger entry.
6. **Cards that don't match any pattern** are flagged `dsl_status: "manual_review"`
   and either hand-authored or deferred.
7. **Build the resolver** in `engine/resolver.py` to interpret the DSL dicts.

## Filter sub-schema (sketch)

```json
{
  "zone": "your_characters" | "opponent_characters" | "your_leader_or_characters" | ...,
  "filter": {
    "subtype_includes": "Straw Hat Crew",
    "attribute_is": "Strike",
    "color_includes": "Red",
    "name_contains": "Luffy",
    "cost_le": 5,
    "power_le": 4000,
    "rested": true | false
  },
  "selection": "player_choice" | "automatic_all" | "random",
  "min": 0,
  "max": 1
}
```

## Acceptance criteria (when picked up)

- [ ] DSL filter sub-schema fully specified
- [ ] All 12 effect verbs from `EFFECT_MAP.md` implemented as DSL ops
- [ ] All 5 combinators implemented
- [ ] `dsl_status: "parsed"` on ≥80% of ST01–ST04 cards
- [ ] All vanilla cards (no effect text) marked `dsl_status: "parsed"` with `triggers: []`
- [ ] All `"manual_review"` cards listed in a report with their `effect_text`
- [ ] At least one full game-playable deck (ST01) has 100% DSL coverage
- [ ] Resolver in `engine/resolver.py` interprets parsed DSL correctly (with tests)

## Related

- `docs/EFFECT_MAP.md` — auto-generated audit of effect_text patterns
- `docs/todos/DSL_PIPELINE.md` — original DSL pipeline TODO (predates this file)
