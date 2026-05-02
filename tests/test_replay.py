"""Tests for engine/replay.py - JSONL trace recording and replay."""
import json
import pytest
from pathlib import Path
from engine.replay import (
    record_action, save_trace, load_trace,
    serialize_action, deserialize_action,
)
from engine.actions import (
    ChooseFirst, AdvancePhase, PlayCard, EndTurn, RespondInput,
    DeclareAttack, DeclareBlocker, PassBlocker, PlayCounter, PassCounter,
    ActivateTrigger, PassTrigger,
)
from engine.game_state import Phase, PlayerID


class TestSerialize:
    def test_choose_first(self):
        action = ChooseFirst("P1")
        assert serialize_action(action) == {"_type": "ChooseFirst", "first_player_id": "P1"}

    def test_advance_phase(self):
        assert serialize_action(AdvancePhase()) == {"_type": "AdvancePhase"}

    def test_play_card(self):
        action = PlayCard("p1-12", extra_don=2)
        assert serialize_action(action) == {
            "_type": "PlayCard", "card_instance_id": "p1-12", "extra_don": 2
        }

    def test_end_turn(self):
        assert serialize_action(EndTurn()) == {"_type": "EndTurn"}

    def test_respond_input(self):
        action = RespondInput(("yes",))
        assert serialize_action(action) == {"_type": "RespondInput", "choices": ["yes"]}

    def test_declare_attack(self):
        action = DeclareAttack("p1-0", "p2-leader")
        assert serialize_action(action) == {
            "_type": "DeclareAttack",
            "attacker_instance_id": "p1-0",
            "target_instance_id": "p2-leader",
        }


class TestDeserialize:
    def test_round_trip_choose_first(self):
        a = ChooseFirst("P2")
        assert deserialize_action(serialize_action(a)) == a

    def test_round_trip_play_card(self):
        a = PlayCard("p1-3", extra_don=0)
        assert deserialize_action(serialize_action(a)) == a

    def test_round_trip_advance_phase(self):
        a = AdvancePhase()
        assert deserialize_action(serialize_action(a)) == a

    def test_round_trip_respond_input(self):
        a = RespondInput(("yes", "no"))
        assert deserialize_action(serialize_action(a)) == a


class TestSaveLoad:
    def test_round_trip_trace(self, tmp_path):
        path = tmp_path / "test_trace.jsonl"
        header = {
            "schema": 1, "seed": 42, "bot_seed": 7,
            "p1_deck": "ST-01", "p2_deck": "ST-02",
            "ruleset_id": "ST01-ST04-v1",
        }
        trace = []
        record_action(trace, ChooseFirst("P1"), turn=1, phase=Phase.SETUP, actor=PlayerID.P1)
        record_action(trace, PlayCard("p1-3"), turn=1, phase=Phase.MAIN, actor=PlayerID.P1)
        save_trace(trace, path, header_meta=header)

        loaded = load_trace(path)
        assert loaded[0]["type"] == "header"
        assert loaded[0]["seed"] == 42
        assert loaded[1]["type"] == "action"
        assert loaded[1]["action"]["_type"] == "ChooseFirst"
        assert loaded[2]["action"]["_type"] == "PlayCard"

    def test_save_creates_jsonl_format(self, tmp_path):
        path = tmp_path / "test.jsonl"
        save_trace([], path, header_meta={"schema": 1})
        content = path.read_text()
        for line in content.strip().split("\n"):
            json.loads(line)
