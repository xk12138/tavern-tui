"""build_turn_messages: system + raw window + replay via parse_input."""

from __future__ import annotations

from tavern.repl import build_system_prompt, build_turn_messages
from tavern.repl.parser import Intent, parse_input
from tavern.save import Save
from tavern.worldpack.loader import load_worldpack


def _load_pack(FIXTURES_DIR):
    return load_worldpack(FIXTURES_DIR / "minimal-ok").pack


def _prime(save: Save, n: int) -> None:
    """Write n player+gm pairs. Player content varies by prefix per turn to
    exercise parse_input's llm_line rebuilding.
    """
    kinds = ['"hi there"', "*I hesitate*", ":look", "just walk in"]
    for i in range(1, n + 1):
        raw = kinds[(i - 1) % len(kinds)]
        save.append_turn("player", raw, turn_no=i)
        save.append_turn("gm", f"gm reply {i}", turn_no=i)
    save.update_state(turn_count=n)


def test_build_system_prompt_includes_world_and_syntax(FIXTURES_DIR):
    pack = _load_pack(FIXTURES_DIR)
    s = build_system_prompt(pack)
    assert "Minimal OK" in s
    assert "neutral" in s               # tone
    assert "input conventions" in s     # INPUT_SYNTAX_PROMPT text
    assert "Previously in this story" not in s   # no summary → no block


def test_build_system_prompt_includes_summary_when_given(FIXTURES_DIR):
    pack = _load_pack(FIXTURES_DIR)
    s = build_system_prompt(pack, summary_text="LOAD BEARING SUMMARY")
    assert "Previously in this story:" in s
    assert "LOAD BEARING SUMMARY" in s


def test_build_turn_messages_short_history(tavern_home, FIXTURES_DIR):
    pack = _load_pack(FIXTURES_DIR)
    save = Save.new("m1", world_id="minimal-ok")
    try:
        _prime(save, 3)
        intent = parse_input('"boss"')
        system, msgs = build_turn_messages(save, pack, intent)

        # No summary yet — cutoff=0, all 3 pairs replayed plus current intent.
        assert "Previously" not in system
        assert len(msgs) == 3 * 2 + 1
        # roles alternate user/assistant/user/assistant/…/user
        assert [m["role"] for m in msgs] == [
            "user", "assistant", "user", "assistant", "user", "assistant", "user"
        ]
        # Current intent is last, and its llm_line has the say-prefix.
        assert msgs[-1]["content"].startswith("Player says (aloud):")
        assert '"boss"' in msgs[-1]["content"]
        # First historical player message was `"hi there"` (say-kind) —
        # verify parse_input reconstructed the same framing.
        assert msgs[0]["role"] == "user"
        assert "Player says (aloud):" in msgs[0]["content"]
        assert "hi there" in msgs[0]["content"]
    finally:
        save.close()


def test_build_turn_messages_respects_window(tavern_home, FIXTURES_DIR):
    pack = _load_pack(FIXTURES_DIR)
    save = Save.new("m1", world_id="minimal-ok")
    try:
        _prime(save, 12)  # 12 pairs — window default is 10
        intent = parse_input("keep walking")
        system, msgs = build_turn_messages(save, pack, intent)
        # 10 pairs × 2 messages + 1 current = 21
        assert len(msgs) == 21
        # First historical user should now be turn 3's player line (turns 1,2 dropped)
        # turn 3 raw was `:look` (idx 2 in kinds).
        assert "quickly does" in msgs[0]["content"]
    finally:
        save.close()


def test_build_turn_messages_with_summary(tavern_home, FIXTURES_DIR):
    pack = _load_pack(FIXTURES_DIR)
    save = Save.new("m1", world_id="minimal-ok")
    try:
        _prime(save, 15)
        save.set_summary("The first 10 turns compressed here.", covered_up_to_turn=10)
        intent = parse_input("what now?")
        system, msgs = build_turn_messages(save, pack, intent)
        # Summary appears in system prompt.
        assert "The first 10 turns compressed here." in system
        assert "Previously in this story:" in system
        # Only turns 11–15 replayed as raw = 5 pairs + 1 current = 11 messages.
        assert len(msgs) == 11
        # Ends with current intent as user.
        assert msgs[-1]["role"] == "user"
        assert "what now?" in msgs[-1]["content"]
    finally:
        save.close()


def test_build_turn_messages_skips_opening_hook(tavern_home, FIXTURES_DIR):
    pack = _load_pack(FIXTURES_DIR)
    save = Save.new("m1", world_id="minimal-ok")
    try:
        # Simulate the opening-hook write at turn_no=0 that _run_play_loop does.
        save.append_turn("system", "You wake up at the counter.", turn_no=0)
        _prime(save, 2)
        intent = parse_input("look")
        _, msgs = build_turn_messages(save, pack, intent)
        # 2 pairs + 1 current — the system row must not sneak in.
        assert len(msgs) == 5
        assert all("wake up at the counter" not in m["content"] for m in msgs)
    finally:
        save.close()
