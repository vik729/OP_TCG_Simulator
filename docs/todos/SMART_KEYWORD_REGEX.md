# TODO: Smart Keyword Regex

> **Status**: Deferred. Vanilla MVP uses hand-authored `cards/keywords/STxx.yaml`
> files instead. Build this when cards beyond ST01–04 are loaded and manual
> entry no longer scales.

## Goal

Replace the hand-authored keyword YAML files with a position-aware regex that
extracts L1 (innate always-on) keywords from `effect_text` directly. Override
file (`cards/keyword_overrides.yaml`) handles the residual misclassifications.

## Why deferred

For 68 cards (ST01–04), hand-authoring is faster and unambiguously correct.
For 1000+ cards across all sets, hand-authoring is impractical and error-prone.
A position-aware regex, derived from analyzing patterns in the loaded card
database, handles 90%+ of cases automatically.

## Approach (when picked up)

1. **Load the full card database** (whatever sets are present at the time).
2. **Cluster effect_text patterns** by:
   - Token position (start of line vs mid-sentence)
   - Preceding context (after `[DON!! xN]`, after `[On X]`, after "gains", etc.)
   - Following context (before punctuation, before "until", etc.)
3. **Derive heuristic rules**:
   - A keyword in `[brackets]` at the start of an effect_text line, or right
     after another bracket-stamp like `[DON!! xN]`, is L1 or L2.
   - A keyword preceded by trigger markers (`[On Play]`, `[On K.O.]`,
     `[When Attacking]`, `[Activate: Main]`) is inside a triggered effect's
     body — likely L3 (skip for L1).
   - A keyword inside running-text words like "gains" / "becomes" is L3.
4. **Implement the regex in `engine/card_db.py`** alongside the existing
   YAML loader. Order: regex first, YAML overrides on top, override file last.
5. **Validate against the existing hand-authored YAMLs** — the regex output
   for ST01–04 should match the YAML entries exactly. Discrepancies are bugs
   in either the regex or the YAML.

## Why this is "data pattern recognition" not pure regex authoring

You can't write the regex from imagination — there are too many edge cases in
real card text. The right workflow is:
- Load all the cards
- Programmatically scan for every bracket token + its context
- Look at the actual frequencies and contexts
- Author rules that cover the dominant cases
- Iterate until the rules cover 90%+ of cards correctly

This is essentially the audit pass that `tools/audit_effects.py` already does
in skeleton form — extend that script to derive regex rules, not just count tokens.

## Acceptance criteria (when picked up)

- [ ] Position-aware regex extracts keywords from at least 90% of loaded cards
      with no manual override required
- [ ] All hand-authored ST01–04 YAML entries are reproduced by the regex
      (with overrides for any genuine edge cases)
- [ ] A scriptable test runs the regex against the full card DB and reports
      coverage and disagreements with overrides
- [ ] `cards/keywords/STxx.yaml` files are deleted after the regex is proven
      to cover them
