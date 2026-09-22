"""Tests for events."""
import pytest


class TestNeowEvent:
    def test_neow_is_first_event(self, game):
        state = game.start(seed="ne1")
        assert state["decision"] == "event_choice"
        assert "Neow" in str(state.get("event_name", ""))

    def test_neow_options(self, game):
        state = game.start(seed="ne2")
        for opt in state["options"]:
            assert "title" in opt
            assert isinstance(opt["title"], str)
            assert "is_locked" in opt

    def test_neow_option_vars(self, game):
        state = game.start(seed="ne3")
        for opt in state["options"]:
            if opt.get("vars"):
                for k, v in opt["vars"].items():
                    assert isinstance(v, (int, float))

    def test_choose_neow(self, game):
        state = game.start(seed="ne4")
        opts = [o for o in state["options"] if not o.get("is_locked")]
        state = game.act("choose_option", option_index=opts[0]["index"])
        assert state.get("decision") is not None


def test_two_card_event_rejects_incomplete_selection(game):
    state = game.start(character="Defect", seed="cheese_selection")
    game.skip_neow(state)
    state = game.enter_room("event", event="ROOM_FULL_OF_CHEESE")
    state = game.act("choose_option", option_index=0)
    assert state["decision"] == "card_select"
    assert state["min_select"] == state["max_select"] == 2
    assert game.act("select_cards", indices="0")["type"] == "error"
    assert game.act("skip_select")["type"] == "error"
    assert game.act("select_cards", indices="0,0")["type"] == "error"
    state = game.act("select_cards", indices="0,1")
    assert state.get("type") != "error", state


class TestEventDescriptions:
    def test_no_ismultiplayer_tag(self, game):
        state = game.start(seed="ed1")
        for opt in state.get("options", []):
            d = opt.get("description") or ""
            assert "IsMultiplayer" not in d
