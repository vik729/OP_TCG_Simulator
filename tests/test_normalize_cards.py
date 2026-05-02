"""
tests/test_normalize_cards.py

Unit tests for the pure normalizer functions in tools/normalize_cards.py.
All tests use synthetic input — no real card files or network access required.
"""

import sys
import pathlib

# Allow importing from tools/ without installing the package
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "tools"))

from normalize_cards import (  # noqa: E402
    normalize_set_id,
    normalize_color,
    normalize_subtypes,
    normalize_int,
    extract_keywords,
    strip_parallel_suffix,
    normalize_card,
)


# ── normalize_set_id ──────────────────────────────────────────────────────────

class TestNormalizeSetId:
    def test_starter_deck(self):
        assert normalize_set_id("ST-01") == "ST01"

    def test_op_set(self):
        assert normalize_set_id("OP-01") == "OP01"

    def test_no_dash(self):
        assert normalize_set_id("ST01") == "ST01"


# ── normalize_color ───────────────────────────────────────────────────────────

class TestNormalizeColor:
    def test_single_color(self):
        assert normalize_color("Red") == ["Red"]

    def test_dual_color(self):
        assert normalize_color("Red/Green") == ["Red", "Green"]

    def test_none_input(self):
        assert normalize_color(None) == []

    def test_empty_string(self):
        assert normalize_color("") == []


# ── normalize_subtypes ────────────────────────────────────────────────────────

class TestNormalizeSubtypes:
    REGISTRY = ["Straw Hat Crew", "Supernovas"]

    def test_single_word(self):
        matched, unknowns = normalize_subtypes("Supernovas", self.REGISTRY)
        assert matched == ["Supernovas"]
        assert unknowns == []

    def test_known_multi_word(self):
        matched, unknowns = normalize_subtypes("Straw Hat Crew", self.REGISTRY)
        assert "Straw Hat Crew" in matched
        assert unknowns == []

    def test_none_input(self):
        assert normalize_subtypes(None, self.REGISTRY) == ([], [])

    def test_empty_string(self):
        assert normalize_subtypes("", self.REGISTRY) == ([], [])

    def test_multi_word_with_extra(self):
        matched, unknowns = normalize_subtypes("Straw Hat Crew Supernovas", self.REGISTRY)
        assert "Straw Hat Crew" in matched
        assert "Supernovas" in matched
        assert unknowns == []

    def test_unknown_token_recorded(self):
        matched, unknowns = normalize_subtypes("Foo Supernovas", self.REGISTRY)
        assert matched == ["Supernovas"]
        assert unknowns == ["Foo"]


# ── normalize_int ─────────────────────────────────────────────────────────────

class TestNormalizeInt:
    def test_integer_input(self):
        assert normalize_int(5000) == 5000

    def test_string_number(self):
        assert normalize_int("2000") == 2000

    def test_none(self):
        assert normalize_int(None) is None

    def test_empty_string(self):
        assert normalize_int("") is None

    def test_invalid_string(self):
        assert normalize_int("N/A") is None


# ── extract_keywords ──────────────────────────────────────────────────────────

class TestExtractKeywords:
    def test_rush(self):
        assert "Rush" in extract_keywords("[Rush] This character can attack on the turn it is played.")

    def test_blocker(self):
        assert "Blocker" in extract_keywords("[Blocker] Activate: Main")

    def test_multiple_keywords(self):
        kws = extract_keywords("[Rush] [Blocker] Some effect text.")
        assert "Rush" in kws
        assert "Blocker" in kws

    def test_no_keywords(self):
        assert extract_keywords("Draw 2 cards.") == []

    def test_none_input(self):
        assert extract_keywords(None) == []

    def test_case_insensitive(self):
        assert "Rush" in extract_keywords("[RUSH] effect")


# ── strip_parallel_suffix ─────────────────────────────────────────────────────

class TestStripParallelSuffix:
    def test_parallel(self):
        assert strip_parallel_suffix("Monkey D. Luffy (Parallel)") == "Monkey D. Luffy"

    def test_alt_art(self):
        assert strip_parallel_suffix("Nami (Alt Art)") == "Nami"

    def test_alt(self):
        assert strip_parallel_suffix("Zoro (Alt)") == "Zoro"

    def test_no_suffix(self):
        assert strip_parallel_suffix("Roronoa Zoro") == "Roronoa Zoro"


# ── normalize_card (integration) ──────────────────────────────────────────────

class TestNormalizeCard:
    RAW_CARD = {
        "card_set_id": "ST01-001",
        "card_name": "Monkey D. Luffy (Parallel)",
        "card_type": "Leader",
        "card_color": "Red",
        "card_cost": None,
        "card_power": "5000",
        "counter_amount": None,
        "life": "5",
        "attribute": "Strike",
        "sub_types": "Straw Hat Crew",
        "rarity": "L",
        "set_id": "ST-01",
        "card_image_id": "ST01-001",
        "card_text": "[Rush] When attacking, K.O. all your opponent's Characters with 3000 power or less.",
    }
    REGISTRY = ["Straw Hat Crew"]

    def _normalize(self):
        return normalize_card(self.RAW_CARD, self.REGISTRY, [])

    def test_output_has_required_keys(self):
        result = self._normalize()
        required = ["id", "name", "type", "color", "cost", "power", "counter",
                    "life", "attribute", "subtypes", "rarity", "set_id",
                    "image_id", "effect_text", "keywords", "triggers", "dsl_status"]
        for key in required:
            assert key in result, f"Missing key: {key}"

    def test_name_stripped(self):
        result = self._normalize()
        assert result["name"] == "Monkey D. Luffy"

    def test_color_normalized(self):
        result = self._normalize()
        assert result["color"] == ["Red"]

    def test_power_as_int(self):
        result = self._normalize()
        assert result["power"] == 5000

    def test_keywords_extracted(self):
        result = self._normalize()
        assert "Rush" in result["keywords"]

    def test_dsl_status_pending(self):
        result = self._normalize()
        assert result["dsl_status"] == "pending"

    def test_triggers_empty(self):
        result = self._normalize()
        assert result["triggers"] == []

    def test_subtypes_resolved_via_registry(self):
        result = self._normalize()
        assert result["subtypes"] == ["Straw Hat Crew"]

    def test_unknown_subtype_logged(self):
        log = []
        raw = dict(self.RAW_CARD, sub_types="Mystery Faction")
        normalize_card(raw, self.REGISTRY, log)
        assert len(log) == 1
        assert log[0]["card_id"] == "ST01-001"
        assert "Mystery" in log[0]["unknown_tokens"]
