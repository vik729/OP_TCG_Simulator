"""Audit effect_text patterns across normalized starter-deck cards.

Purpose
-------
Before designing the Effect DSL schema (Phase 1d), survey the actual language
used in effect_text across ST01-ST04. This script extracts structural
patterns (bracket tokens, verbs, targeting phrases, conditionals, costs) and
produces:

  1. A machine-readable JSON report (docs/effect_audit.json)
  2. A human-readable Markdown report (docs/EFFECT_MAP.md)

Run:
    python tools/audit_effects.py
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
CARDS_DIR = REPO_ROOT / "cards"
DOCS_DIR = REPO_ROOT / "docs"

SETS = ["ST01", "ST02", "ST03", "ST04"]

TRIGGER_TOKENS = {
    "[On Play]", "[When Attacking]", "[On K.O.]", "[On Block]",
    "[End of Your Turn]", "[Start of Your Turn]", "[Counter]",
    "[Trigger]", "[Your Turn]", "[Opponent's Turn]",
    "[Main]", "[Activate: Main]",
}

STATIC_OR_COST_TOKENS = {
    "[DON!! x1]", "[DON!! x2]", "[DON!! x3]", "[DON!! x4]",
    "[Once Per Turn]",
}

KEYWORD_TOKENS = {
    "[Blocker]", "[Rush]", "[Banish]", "[Double Attack]",
}

EFFECT_VERB_PATTERNS = [
    ("Draw",        re.compile(r"\bdraw\s+\d+\s+cards?\b", re.IGNORECASE)),
    ("KO",          re.compile(r"\bK\.?O\.?\b")),
    ("Bounce",      re.compile(r"\breturn\s+.*?to\s+(?:the\s+)?owner'?s?\s+hand\b", re.IGNORECASE)),
    ("BounceSelf",  re.compile(r"\breturn\s+this\s+card\s+to\s+", re.IGNORECASE)),
    ("GivePower",   re.compile(r"(?:gains?|\+)\s*\+?\d+\s*power", re.IGNORECASE)),
    ("AttachDon",   re.compile(r"\bgive\s+.*?DON!!\s+cards?\b", re.IGNORECASE)),
    ("AddDon",      re.compile(r"\badd\s+up\s+to\s+\d+\s+DON!!\s+cards?\s+from\s+your\s+DON!!\s+deck\b", re.IGNORECASE)),
    ("RestTarget",  re.compile(r"\brest\s+up\s+to\s+\d+\s+of\s+your\s+opponent'?s?\b", re.IGNORECASE)),
    ("SetActive",   re.compile(r"\bset\s+.*?as\s+active\b", re.IGNORECASE)),
    ("LookAt",      re.compile(r"\blook\s+at\s+\d+\s+cards?\s+from\s+the\s+top\b", re.IGNORECASE)),
    ("Search",      re.compile(r"\bsearch\s+your\s+deck\b", re.IGNORECASE)),
    ("AddFromDeck", re.compile(r"\badd\s+up\s+to\s+\d+\s+.*?\s+from\s+your\s+deck\b", re.IGNORECASE)),
    ("Play",        re.compile(r"\bplay\s+up\s+to\s+\d+\s+", re.IGNORECASE)),
    ("TrashHand",   re.compile(r"\btrash\s+\d+\s+cards?\s+from\s+your\s+hand\b", re.IGNORECASE)),
    ("TrashDeck",   re.compile(r"\btrash\s+the\s+top\s+\d+\s+cards?\s+of\s+your\s+deck\b", re.IGNORECASE)),
    ("GainKeyword", re.compile(r"\bgains?\s+\[(?:Rush|Blocker|Banish|Double Attack)\]", re.IGNORECASE)),
]

TARGET_PATTERNS = [
    ("self:this_card",             re.compile(r"\bthis\s+(?:card|Character|Leader)\b", re.IGNORECASE)),
    ("own:leader_or_character",    re.compile(r"your\s+Leader\s+or\s+(?:1\s+of\s+your\s+)?Characters?", re.IGNORECASE)),
    ("own:character",              re.compile(r"\b(?:up\s+to\s+\d+\s+of\s+)?your\s+Characters?\b", re.IGNORECASE)),
    ("opp:character",              re.compile(r"your\s+opponent'?s?\s+Characters?", re.IGNORECASE)),
    ("opp:don",                    re.compile(r"your\s+opponent'?s?\s+DON!!\s+cards?", re.IGNORECASE)),
    ("opp:blocker_restriction",    re.compile(r"your\s+opponent\s+cannot\s+activate\s+\[Blocker\]", re.IGNORECASE)),
    ("filter:cost_le",             re.compile(r"cost\s+of\s+\d+\s+or\s+less", re.IGNORECASE)),
    ("filter:power_le",            re.compile(r"\d+\s+power\s+or\s+less", re.IGNORECASE)),
    ("filter:subtype",             re.compile(r"[{\"][A-Za-z][^}\"]*[}\"]\s+type", re.IGNORECASE)),
    ("filter:rested",              re.compile(r"\brested\s+(?:Character|DON)", re.IGNORECASE)),
    ("scope:other_than_this_card", re.compile(r"other\s+than\s+this\s+card", re.IGNORECASE)),
]

CLAUSE_PATTERNS = [
    ("conditional:if",         re.compile(r"\bIf\b", re.IGNORECASE)),
    ("choice:up_to",           re.compile(r"\bup\s+to\s+\d+\b", re.IGNORECASE)),
    ("choice:you_may",         re.compile(r"\byou\s+may\b", re.IGNORECASE)),
    ("choice:then",            re.compile(r",\s*then\b", re.IGNORECASE)),
    ("cost:don_minus",         re.compile(r"DON!!\s*-\s*\d+", re.IGNORECASE)),
    ("cost:paren_rest",        re.compile(r"\(\d+\)\s*\(You may rest", re.IGNORECASE)),
    ("cost:you_may_rest_self", re.compile(r"You may rest this (?:card|Stage)", re.IGNORECASE)),
    ("cost:trash_hand",        re.compile(r"You may trash \d+ cards? from your hand", re.IGNORECASE)),
    ("opponent_mentioned",     re.compile(r"\bopponent'?s?\b", re.IGNORECASE)),
    ("per_turn_limit",         re.compile(r"\[Once Per Turn\]", re.IGNORECASE)),
]


@dataclass
class CardRow:
    card_id: str
    set_id: str
    type: str
    effect_text: str
    bracket_tokens: list = field(default_factory=list)
    triggers: list = field(default_factory=list)
    verbs: list = field(default_factory=list)
    targets: list = field(default_factory=list)
    clauses: list = field(default_factory=list)
    has_trigger_tail: bool = False
    is_vanilla: bool = False


BRACKET_RE = re.compile(r"\[[^\]]+\]")
PAREN_RE = re.compile(r"\([^)]*\)")


def _clean_effect_text(raw) -> str:
    if raw is None:
        return ""
    s = str(raw).strip()
    if s.upper() == "NULL":
        return ""
    return s


def strip_reminder_text(text: str) -> str:
    return PAREN_RE.sub("", text).strip()


def classify_card(card: dict) -> CardRow:
    row = CardRow(
        card_id=card["id"],
        set_id=card.get("set_id") or card["id"].split("-")[0],
        type=card.get("type", "?"),
        effect_text=_clean_effect_text(card.get("effect_text")),
    )
    if not row.effect_text.strip():
        row.is_vanilla = True
        return row

    stripped = strip_reminder_text(row.effect_text)
    brackets = BRACKET_RE.findall(row.effect_text)
    row.bracket_tokens = brackets
    row.has_trigger_tail = "[Trigger]" in brackets

    for tok in brackets:
        if tok in TRIGGER_TOKENS:
            row.triggers.append(tok)
    for name, pat in EFFECT_VERB_PATTERNS:
        if pat.search(stripped):
            row.verbs.append(name)
    for name, pat in TARGET_PATTERNS:
        if pat.search(stripped):
            row.targets.append(name)
    for name, pat in CLAUSE_PATTERNS:
        if pat.search(row.effect_text):
            row.clauses.append(name)
    return row


def load_all_cards():
    cards = []
    for set_id in SETS:
        for path in sorted((CARDS_DIR / set_id).glob("*.json")):
            with path.open(encoding="utf-8") as fh:
                cards.append(json.load(fh))
    return cards


def build_report(rows, raw_cards=None):
    rows = list(rows)
    null_string_cards = []
    if raw_cards is not None:
        for rc in raw_cards:
            et = rc.get("effect_text")
            if isinstance(et, str) and et.strip().upper() == "NULL":
                null_string_cards.append(rc["id"])

    bracket_counter = Counter()
    trigger_counter = Counter()
    verb_counter = Counter()
    target_counter = Counter()
    clause_counter = Counter()
    grouped = defaultdict(list)
    vanilla = []
    trigger_tail_cards = []
    unknown_brackets = Counter()
    per_set = {s: Counter() for s in SETS}

    for row in rows:
        if row.is_vanilla:
            vanilla.append(row.card_id)
            grouped["(vanilla)"].append({"id": row.card_id, "type": row.type, "effect_text": ""})
            continue
        for tok in row.bracket_tokens:
            bracket_counter[tok] += 1
            if (tok not in TRIGGER_TOKENS and tok not in STATIC_OR_COST_TOKENS
                    and tok not in KEYWORD_TOKENS):
                unknown_brackets[tok] += 1
        for t in row.triggers:
            trigger_counter[t] += 1
        for v in row.verbs:
            verb_counter[v] += 1
            per_set[row.set_id][v] += 1
        for t in row.targets:
            target_counter[t] += 1
        for c in row.clauses:
            clause_counter[c] += 1
        if row.has_trigger_tail:
            trigger_tail_cards.append(row.card_id)
        group_key = next(
            (tok for tok in row.bracket_tokens if tok in TRIGGER_TOKENS),
            "(static/keyword only)",
        )
        grouped[group_key].append({
            "id": row.card_id, "type": row.type,
            "effect_text": row.effect_text,
            "verbs": row.verbs, "targets": row.targets,
        })

    no_verb = [
        {"id": r.card_id, "effect_text": r.effect_text}
        for r in rows if not r.is_vanilla and not r.verbs
    ]

    return {
        "totals": {
            "cards": len(rows), "vanilla": len(vanilla),
            "with_effect_text": len(rows) - len(vanilla),
            "trigger_tail_cards": len(trigger_tail_cards),
        },
        "bracket_tokens": bracket_counter.most_common(),
        "unknown_brackets": unknown_brackets.most_common(),
        "triggers": trigger_counter.most_common(),
        "verbs": verb_counter.most_common(),
        "targets": target_counter.most_common(),
        "clauses": clause_counter.most_common(),
        "per_set_verbs": {s: dict(c.most_common()) for s, c in per_set.items()},
        "grouped_by_trigger": dict(grouped),
        "vanilla_cards": vanilla,
        "trigger_tail_cards": trigger_tail_cards,
        "no_verb_detected": no_verb,
        "data_quality": {"effect_text_literal_NULL": null_string_cards},
    }


def _table(headers, rows):
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join(["---"] * len(headers)) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(c) for c in r) + " |")
    return "\n".join(out)


def render_markdown(report):
    t = report["totals"]
    L = []
    L.append("# Effect Text Audit - ST01-ST04")
    L.append("")
    L.append("> Auto-generated by `tools/audit_effects.py`. Do not hand-edit.")
    L.append(">")
    L.append("> **{} cards**  |  {} with effect text  |  {} vanilla  |  {} have a `[Trigger]` tail".format(
        t["cards"], t["with_effect_text"], t["vanilla"], t["trigger_tail_cards"]))
    L.append("")

    L.append("## 1. Bracket tokens")
    L.append("")
    L.append("Every bracketed token found in effect_text, with frequency. "
             "Tokens fall into three roles: **trigger** (when the effect fires), "
             "**static/cost** (conditions on activation), and **keyword** "
             "(ability granted to the card).")
    L.append("")
    L.append(_table(["Token", "Count", "Role"], [
        [tok, n,
         "trigger" if tok in TRIGGER_TOKENS
         else "cost/static" if tok in STATIC_OR_COST_TOKENS
         else "keyword" if tok in KEYWORD_TOKENS
         else "?unknown?"]
        for tok, n in report["bracket_tokens"]
    ]))
    L.append("")
    if report["unknown_brackets"]:
        L.append("Unknown bracket tokens (not yet in the taxonomy):")
        L.append("")
        for tok, n in report["unknown_brackets"]:
            L.append("- `{}` x {}".format(tok, n))
        L.append("")

    L.append("## 2. Trigger types")
    L.append("")
    L.append(_table(["Trigger", "Count"], [[tok, n] for tok, n in report["triggers"]]))
    L.append("")

    L.append("## 3. Effect verbs (candidate DSL primitives)")
    L.append("")
    L.append("Each row is a candidate atomic op in the DSL. Priority = implement high-count rows first.")
    L.append("")
    L.append(_table(
        ["Verb", "Count", "ST01", "ST02", "ST03", "ST04"],
        [[name, n,
          report["per_set_verbs"]["ST01"].get(name, 0),
          report["per_set_verbs"]["ST02"].get(name, 0),
          report["per_set_verbs"]["ST03"].get(name, 0),
          report["per_set_verbs"]["ST04"].get(name, 0)]
         for name, n in report["verbs"]]
    ))
    L.append("")

    L.append("## 4. Targeting patterns")
    L.append("")
    L.append("Patterns the target-selection DSL has to express.")
    L.append("")
    L.append(_table(["Pattern", "Count"], [[n, c] for n, c in report["targets"]]))
    L.append("")

    L.append("## 5. Clauses - conditionals, choice, cost")
    L.append("")
    L.append("Signals for which DSL combinators and cost shapes are needed.")
    L.append("")
    L.append(_table(["Clause", "Count"], [[n, c] for n, c in report["clauses"]]))
    L.append("")

    L.append("## 6. Cards grouped by trigger")
    L.append("")
    L.append("Full `effect_text` listed so patterns across cards within the same trigger can be compared side-by-side.")
    L.append("")
    ordered = []
    for tok in TRIGGER_TOKENS:
        if tok in report["grouped_by_trigger"]:
            ordered.append(tok)
    for k in report["grouped_by_trigger"]:
        if k not in ordered and k != "(vanilla)":
            ordered.append(k)
    if "(vanilla)" in report["grouped_by_trigger"]:
        ordered.append("(vanilla)")

    for key in ordered:
        entries = report["grouped_by_trigger"][key]
        L.append("### `{}` - {} card(s)".format(key, len(entries)))
        L.append("")
        for e in entries:
            if e.get("effect_text"):
                verbs = ", ".join(e.get("verbs") or []) or "-"
                L.append("- **{}** ({}) - verbs: _{}_".format(e["id"], e["type"], verbs))
                L.append("    > " + e["effect_text"])
            else:
                L.append("- **{}** ({}) - vanilla".format(e["id"], e["type"]))
        L.append("")

    dq = report.get("data_quality", {}).get("effect_text_literal_NULL") or []
    if dq:
        L.append("## 7. Data-quality findings")
        L.append("")
        L.append("**effect_text is the literal string \"NULL\"** on {} card(s). "
                 "These should be normalized to empty string or JSON null in "
                 "`normalize_cards.py` so downstream tools don't have to "
                 "special-case the literal.".format(len(dq)))
        L.append("")
        for cid in dq:
            L.append("- `{}`".format(cid))
        L.append("")

    if report["no_verb_detected"]:
        L.append("## 8. Cards with no verb detected")
        L.append("")
        L.append("These have effect text but none of the known verb patterns "
                 "fired. Either the regex taxonomy is missing something, or "
                 "these cards are pure keyword-granters (e.g. `[Blocker]`, `[Rush]`).")
        L.append("")
        for e in report["no_verb_detected"]:
            L.append("- **{}** - {}".format(e["id"], e["effect_text"]))
        L.append("")

    return "\n".join(L)


def main():
    cards = load_all_cards()
    rows = [classify_card(c) for c in cards]
    report = build_report(rows, raw_cards=cards)
    DOCS_DIR.mkdir(exist_ok=True)
    (DOCS_DIR / "effect_audit.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    (DOCS_DIR / "EFFECT_MAP.md").write_text(render_markdown(report), encoding="utf-8")
    print("Audited {} cards.".format(report["totals"]["cards"]))
    print("  with effect text: {}".format(report["totals"]["with_effect_text"]))
    print("  vanilla:          {}".format(report["totals"]["vanilla"]))
    print("Wrote {}".format(DOCS_DIR / "effect_audit.json"))
    print("Wrote {}".format(DOCS_DIR / "EFFECT_MAP.md"))


if __name__ == "__main__":
    main()
