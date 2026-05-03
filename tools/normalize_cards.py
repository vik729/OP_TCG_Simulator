"""
normalize_cards.py - Phase 2: Normalize raw API data to base card schema

Reads raw JSON files from cards/raw/decks/ and writes one normalized JSON
file per card into cards/STxx/. Safe to re-run - overwrites existing files
with the latest normalized output.

Pipeline:
    1. Load raw API dump.
    2. Transform each card to the base schema (normalize_card).
       - Subtypes tokenized against cards/subtypes.json (longest-match-first,
         case-insensitive, emits canonical spelling).
       - effect_text sentinel 'NULL' -> JSON null.
    3. Overlay cards/corrections.json on top (apply_corrections).
    4. Write cards/STxx/<id>.json.
    5. Write a human-readable run report to docs/normalization_report.md.

Usage:
    python tools/normalize_cards.py          # warn on unknown subtypes
    python tools/normalize_cards.py --strict # fail on unknown subtypes (CI)
"""

import argparse
import datetime
import json
import pathlib
import re
import sys

# --- Config ----------------------------------------------------------------

PROJECT_ROOT = pathlib.Path(__file__).parent.parent
RAW_DECKS_DIR = PROJECT_ROOT / "cards" / "raw" / "decks"
RAW_SETS_DIR = PROJECT_ROOT / "cards" / "raw" / "sets"
RAW_DIR = RAW_DECKS_DIR  # back-compat for code that hasn't been updated
CARDS_DIR = PROJECT_ROOT / "cards"
CORRECTIONS_FILE = PROJECT_ROOT / "cards" / "corrections.json"
SUBTYPES_FILE = PROJECT_ROOT / "cards" / "subtypes.json"
DOCS_DIR = PROJECT_ROOT / "docs"
REPORT_FILE = DOCS_DIR / "normalization_report.md"

# All sets we know how to normalize. Extend by running fetch_all_sets.py
# and adding the resulting set IDs here.
TARGET_DECKS = ["ST-01", "ST-02", "ST-03", "ST-04"]

KNOWN_KEYWORDS = [
    "Rush",
    "Blocker",
    "Banish",
    "Double Attack",
    "Unblockable",
]


# --- Subtype registry -----------------------------------------------------


def load_subtype_registry():
    """Load the canonical subtype list from cards/subtypes.json.

    Supports both {"subtypes": [...]} object form and raw list form for
    flexibility. Keys starting with _ are meta and ignored.
    """
    if not SUBTYPES_FILE.exists():
        return []
    data = json.loads(SUBTYPES_FILE.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        return list(data.get("subtypes", []))
    return list(data)


def normalize_subtypes(raw, registry):
    """Tokenize `raw` using longest-prefix-first matching against `registry`.

    - Case-insensitive match; emits the canonical form from `registry`.
    - Returns (matched_subtypes, unknown_tokens).
    - Unknown tokens are single whitespace-delimited words that don't start
      any registry entry; the matcher continues past them instead of hanging.
    """
    if not raw:
        return [], []

    by_len = sorted(registry, key=len, reverse=True)
    remaining = raw.strip()
    result = []
    unknown = []

    while remaining:
        remaining_lower = remaining.lower()
        matched = None
        for entry in by_len:
            entry_lower = entry.lower()
            if not remaining_lower.startswith(entry_lower):
                continue
            # Enforce a word boundary: next char must be end-of-string
            # or whitespace. Prevents e.g. 'Navy' from matching 'NavyBlue'.
            tail_idx = len(entry)
            if tail_idx == len(remaining) or remaining[tail_idx].isspace():
                matched = entry  # canonical form
                break

        if matched:
            result.append(matched)
            remaining = remaining[len(matched):].lstrip()
        else:
            # Consume the next whitespace-delimited word as unknown.
            word, _, rest = remaining.partition(" ")
            unknown.append(word)
            remaining = rest.strip()

    return result, unknown


# --- Other normalizers ----------------------------------------------------


def normalize_set_id(raw_set_id):
    return raw_set_id.replace("-", "")


def normalize_color(raw_color):
    if not raw_color:
        return []
    return [c.strip() for c in raw_color.split("/")]


def normalize_int(value):
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _clean_effect_text(raw):
    """Convert the upstream API's sentinel 'NULL' string to JSON null."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s or s.upper() == "NULL":
        return None
    return s


def extract_keywords(effect_text):
    if not effect_text:
        return []
    found = []
    for kw in KNOWN_KEYWORDS:
        pattern = r"\[" + re.escape(kw) + r"\]"
        if re.search(pattern, effect_text, re.IGNORECASE):
            found.append(kw)
    return found


def strip_parallel_suffix(name):
    return re.sub(r"\s*\(Parallel\)|\s*\(Alt Art\)|\s*\(Alt\)", "", name).strip()


def normalize_card(raw, registry, unknown_subtypes_log):
    raw_set_id = raw.get("set_id", "")
    effect_text = _clean_effect_text(raw.get("card_text"))
    subtypes, unknowns = normalize_subtypes(raw.get("sub_types"), registry)
    if unknowns:
        unknown_subtypes_log.append({
            "card_id": raw.get("card_set_id", "?"),
            "raw": raw.get("sub_types"),
            "unknown_tokens": unknowns,
        })
    return {
        "id": raw.get("card_set_id", ""),
        "name": strip_parallel_suffix(raw.get("card_name", "")),
        "type": raw.get("card_type", ""),
        "color": normalize_color(raw.get("card_color")),
        "cost": normalize_int(raw.get("card_cost")),
        "power": normalize_int(raw.get("card_power")),
        "counter": normalize_int(raw.get("counter_amount")),
        "life": normalize_int(raw.get("life")),
        "attribute": raw.get("attribute") or None,
        "subtypes": subtypes,
        "rarity": raw.get("rarity") or None,
        "set_id": normalize_set_id(raw_set_id),
        "image_id": raw.get("card_image_id") or raw.get("card_set_id", ""),
        "effect_text": effect_text,
        "keywords": extract_keywords(effect_text),
        "triggers": [],
        "dsl_status": "pending",
    }


# --- Corrections overlay ---------------------------------------------------


def load_corrections():
    if not CORRECTIONS_FILE.exists():
        return {}
    data = json.loads(CORRECTIONS_FILE.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


def apply_corrections(card, corrections):
    outcomes = []
    card_id = card.get("id")
    entry = corrections.get(card_id)
    if not entry:
        return card, outcomes

    reason = entry.get("_reason")
    corrected = dict(card)

    for field, override in entry.items():
        if field.startswith("_"):
            continue
        if not isinstance(override, dict) or "after" not in override:
            corrected[field] = override
            outcomes.append({
                "card_id": card_id, "field": field,
                "status": "applied-direct", "reason": reason,
            })
            continue

        current = card.get(field)
        before = override.get("before_contains")
        after = override["after"]

        if isinstance(current, str) and before and before in current:
            corrected[field] = after
            outcomes.append({"card_id": card_id, "field": field, "status": "applied", "reason": reason})
        elif current == after:
            outcomes.append({"card_id": card_id, "field": field, "status": "skipped-upstream-fixed", "reason": reason})
        else:
            outcomes.append({
                "card_id": card_id, "field": field, "status": "stale", "reason": reason,
                "detail": "current value neither contains `before_contains` nor equals `after`",
                "current": current,
            })
    return corrected, outcomes


# --- Reporting -------------------------------------------------------------


def write_report(outcomes, nulls_converted, unknown_subtypes_log, total_cards, registry_size):
    DOCS_DIR.mkdir(exist_ok=True)

    applied = [o for o in outcomes if o["status"] in ("applied", "applied-direct")]
    skipped = [o for o in outcomes if o["status"] == "skipped-upstream-fixed"]
    stale = [o for o in outcomes if o["status"] == "stale"]

    L = []
    L.append("# Normalization report")
    L.append("")
    L.append("> Auto-generated by `tools/normalize_cards.py`. Do not hand-edit.")
    L.append(">")
    L.append("> Last run: " + datetime.date.today().isoformat())
    L.append(">")
    L.append("> Cards normalized: {} | subtype registry: {} entries | corrections applied: {} | skipped: {} | stale: {} | NULL->null: {} | unknown subtypes on {} card(s)".format(
        total_cards, registry_size, len(applied), len(skipped), len(stale),
        len(nulls_converted), len(unknown_subtypes_log)))
    L.append("")

    L.append("## Corrections applied ({})".format(len(applied)))
    L.append("")
    if applied:
        for o in applied:
            L.append("- **{}** . `{}` . {}".format(o["card_id"], o["field"], o.get("reason") or "(no reason given)"))
    else:
        L.append("_(none)_")
    L.append("")

    L.append("## Corrections skipped - upstream fixed ({})".format(len(skipped)))
    L.append("")
    if skipped:
        L.append("Consider removing these entries from `cards/corrections.json`.")
        L.append("")
        for o in skipped:
            L.append("- **{}** . `{}`".format(o["card_id"], o["field"]))
    else:
        L.append("_(none)_")
    L.append("")

    L.append("## Corrections stale ({})".format(len(stale)))
    L.append("")
    if stale:
        L.append("Raw value neither contains `before_contains` nor equals `after`. Investigate before the next run.")
        L.append("")
        for o in stale:
            L.append("- **{}** . `{}` . current: `{}`".format(o["card_id"], o["field"], (str(o.get("current") or ""))[:120]))
    else:
        L.append("_(none)_")
    L.append("")

    L.append("## Unknown subtypes ({})".format(len(unknown_subtypes_log)))
    L.append("")
    if unknown_subtypes_log:
        L.append("Cards where the registry-based matcher encountered tokens it could not resolve. Either add the new subtype to `cards/subtypes.json` or add a correction for the garbled upstream data.")
        L.append("")
        for u in unknown_subtypes_log:
            L.append("- **{}** . raw: `{}` . unknown tokens: `{}`".format(
                u["card_id"], u["raw"], ", ".join(u["unknown_tokens"])))
    else:
        L.append("_(none)_  All subtypes matched the registry cleanly.")
    L.append("")

    L.append("## `\"NULL\"` -> null conversions on `effect_text` ({})".format(len(nulls_converted)))
    L.append("")
    if nulls_converted:
        for cid in nulls_converted:
            L.append("- `{}`".format(cid))
    else:
        L.append("_(none)_")
    L.append("")

    REPORT_FILE.write_text("\n".join(L), encoding="utf-8")


# --- Main ------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1] if __doc__ else "")
    parser.add_argument(
        "--strict", action="store_true",
        help="Exit non-zero if any unknown subtypes are encountered (for CI).",
    )
    args = parser.parse_args()

    corrections = load_corrections()
    registry = load_subtype_registry()
    total_cards = 0
    total_sets = 0
    all_outcomes = []
    nulls_converted = []
    unknown_subtypes_log = []

    if not registry:
        print("[WARN] cards/subtypes.json is empty or missing; subtype normalization will flag everything as unknown.")

    # Discover every raw file present (both /decks/ and /sets/).
    raw_files = []
    if RAW_DECKS_DIR.exists():
        raw_files.extend(sorted(RAW_DECKS_DIR.glob("*.json")))
    if RAW_SETS_DIR.exists():
        raw_files.extend(sorted(RAW_SETS_DIR.glob("*.json")))

    if not raw_files:
        print("[ERROR] No raw files found. Run tools/fetch_all_sets.py first.")
        return

    for raw_path in raw_files:
        deck_id = raw_path.stem  # e.g. "ST-01" or "OP-03"

        raw_cards = json.loads(raw_path.read_text(encoding="utf-8"))
        set_id_normalized = normalize_set_id(deck_id)
        out_dir = CARDS_DIR / set_id_normalized
        out_dir.mkdir(parents=True, exist_ok=True)

        print("[NORMALIZE] {} -> cards/{}/ ({} cards)".format(deck_id, set_id_normalized, len(raw_cards)))

        for raw_card in raw_cards:
            rct = raw_card.get("card_text")
            if isinstance(rct, str) and rct.strip().upper() == "NULL":
                nulls_converted.append(raw_card.get("card_set_id", "?"))

            normalized = normalize_card(raw_card, registry, unknown_subtypes_log)
            card_id = normalized["id"]
            if not card_id:
                print("  [WARN] Card missing ID, skipping: {}".format(raw_card))
                continue

            corrected, outcomes = apply_corrections(normalized, corrections)
            for o in outcomes:
                status = o["status"]
                if status == "applied":
                    print("  [CORRECTION applied] {} . {} . {}".format(
                        o["card_id"], o["field"], (str(o.get("reason") or ""))[:80]))
                elif status == "applied-direct":
                    print("  [CORRECTION direct]  {} . {}".format(o["card_id"], o["field"]))
                elif status == "skipped-upstream-fixed":
                    print("  [CORRECTION skipped] {} . {} (upstream fixed)".format(o["card_id"], o["field"]))
                elif status == "stale":
                    print("  [CORRECTION STALE!!] {} . {} - raw shape changed".format(o["card_id"], o["field"]))
            all_outcomes.extend(outcomes)

            out_path = out_dir / "{}.json".format(card_id)
            out_path.write_text(
                json.dumps(corrected, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

        total_cards += len(raw_cards)
        total_sets += 1
        print("  -> Written {} cards to cards/{}/".format(len(raw_cards), set_id_normalized))

    # Log unknown subtypes to stdout
    for u in unknown_subtypes_log:
        print("  [SUBTYPE unknown]   {} . raw={!r} . unknown_tokens={}".format(
            u["card_id"], u["raw"], u["unknown_tokens"]))

    write_report(all_outcomes, nulls_converted, unknown_subtypes_log, total_cards, len(registry))

    print("")
    print("Done. {} cards across {} sets written to {}".format(total_cards, total_sets, CARDS_DIR))
    print("  subtype registry:     {} entries".format(len(registry)))
    print("  corrections applied:  {}".format(
        sum(1 for o in all_outcomes if o["status"] in ("applied", "applied-direct"))))
    print("  corrections skipped:  {} (upstream fixed)".format(
        sum(1 for o in all_outcomes if o["status"] == "skipped-upstream-fixed")))
    print("  corrections stale:    {} (investigate!)".format(
        sum(1 for o in all_outcomes if o["status"] == "stale")))
    print("  NULL->null converted: {}".format(len(nulls_converted)))
    print("  unknown subtypes:     {} card(s)".format(len(unknown_subtypes_log)))
    print("Report written to {}".format(REPORT_FILE))

    if args.strict and unknown_subtypes_log:
        print("\n[STRICT] {} card(s) have unknown subtypes; exiting non-zero.".format(len(unknown_subtypes_log)))
        sys.exit(1)


if __name__ == "__main__":
    main()
