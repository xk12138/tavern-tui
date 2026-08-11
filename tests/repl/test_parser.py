"""Tests for the input-prefix parser.

Pure-function tests — no fixtures needed beyond stdlib.
"""

from __future__ import annotations

from tavern.repl.parser import (
    INPUT_SYNTAX_PROMPT,
    SHORTCUT_MAP,
    Intent,
    parse_input,
)


# ── slash ────────────────────────────────────────────────────────────────


def test_slash_command():
    i = parse_input("/save keypoint")
    assert i.kind == "slash"
    # slash preserves the leading slash so the CLI handler can dispatch.
    assert i.body == "/save keypoint"
    assert i.llm_line == ""


def test_slash_just_the_slash():
    i = parse_input("/")
    assert i.kind == "slash"


# ── say ──────────────────────────────────────────────────────────────────


def test_say_basic():
    i = parse_input('"老板,来一壶酒"')
    assert i.kind == "say"
    assert i.body == "老板,来一壶酒"
    assert i.raw == '"老板,来一壶酒"'
    assert i.llm_line == 'Player says (aloud): "老板,来一壶酒"'


def test_say_english():
    i = parse_input('"Hello there"')
    assert i.kind == "say"
    assert i.body == "Hello there"


def test_say_empty_quotes_still_counts_as_say():
    # """" is a boundary case — technically valid say with empty body.
    # We accept it rather than special-case; the LLM gets an empty line.
    i = parse_input('""')
    assert i.kind == "say"
    assert i.body == ""


# ── think ────────────────────────────────────────────────────────────────


def test_think_basic():
    i = parse_input("*这人看我的眼神不对劲*")
    assert i.kind == "think"
    assert i.body == "这人看我的眼神不对劲"
    assert "internal" in i.llm_line
    assert "unheard" in i.llm_line


def test_think_english():
    i = parse_input("*I don't trust her*")
    assert i.kind == "think"
    assert i.body == "I don't trust her"


# ── shortcut ────────────────────────────────────────────────────────────


def test_shortcut_look_known():
    i = parse_input(":look")
    assert i.kind == "shortcut"
    assert i.body == "look"
    assert "looks around" in i.llm_line


def test_shortcut_wait_known():
    i = parse_input(":wait")
    assert i.kind == "shortcut"
    assert "waits" in i.llm_line


def test_shortcut_unknown_passthrough():
    # Unknown shortcuts flow through as-is; worldpacks can invent their own.
    i = parse_input(":ponder")
    assert i.kind == "shortcut"
    assert i.body == "ponder"
    assert i.llm_line == "Player quickly does: ponder"


def test_shortcut_just_colon_is_action():
    # `:` alone has no body → fall back to action.
    i = parse_input(":")
    assert i.kind == "action"


def test_every_shortcut_in_map_covered():
    # SHORTCUT_MAP shouldn't shrink silently — regressions here mean the
    # docstring & USAGE.md hint list drift out of sync.
    expected = {"look", "wait", "rest", "inventory", "map", "recap"}
    assert set(SHORTCUT_MAP) == expected
    for key in SHORTCUT_MAP:
        i = parse_input(f":{key}")
        assert i.kind == "shortcut"
        assert i.llm_line != f"Player quickly does: {key}", (
            f"expected {key!r} to be expanded, not passthrough"
        )


# ── action (default) ────────────────────────────────────────────────────


def test_action_default():
    i = parse_input("我走到吧台")
    assert i.kind == "action"
    assert i.body == "我走到吧台"
    assert i.llm_line == "Player does: 我走到吧台"


def test_action_english():
    i = parse_input("walk to the bar")
    assert i.kind == "action"


# ── boundary cases ──────────────────────────────────────────────────────


def test_unclosed_quote_is_action():
    """Prefix must match at BOTH ends; only-opening is free-form."""
    i = parse_input('"没关掉的引号')
    assert i.kind == "action"
    assert i.body == '"没关掉的引号'


def test_unclosed_star_is_action():
    i = parse_input("*unfinished")
    assert i.kind == "action"


def test_only_closing_char_is_action():
    i = parse_input('foo"')
    assert i.kind == "action"


def test_single_quote_char_is_action():
    # Length-1 can't be both prefix and closing.
    i = parse_input('"')
    assert i.kind == "action"


def test_whitespace_stripped():
    i = parse_input('   "hello"   ')
    assert i.kind == "say"
    assert i.body == "hello"


def test_empty_input_becomes_action():
    # REPL usually filters empty lines before parser sees them, but the
    # parser shouldn't blow up.
    i = parse_input("")
    assert i.kind == "action"
    assert i.body == ""


def test_whitespace_only_becomes_action():
    i = parse_input("   ")
    assert i.kind == "action"


# ── llm_line format ─────────────────────────────────────────────────────


def test_llm_line_shapes():
    """Snapshot the exact llm_line format — GM prompt depends on this."""
    assert parse_input('"hi"').llm_line == 'Player says (aloud): "hi"'
    assert parse_input("*hi*").llm_line == (
        'Player thinks (internal, unheard by others): "hi"'
    )
    assert parse_input(":look").llm_line == (
        "Player quickly does: looks around, taking in the scene"
    )
    assert parse_input("do X").llm_line == "Player does: do X"
    assert parse_input("/save").llm_line == ""


# ── system prompt fragment ──────────────────────────────────────────────


def test_input_syntax_prompt_mentions_all_prefixes():
    assert '"..."' in INPUT_SYNTAX_PROMPT
    assert "*...*" in INPUT_SYNTAX_PROMPT
    assert ":xxx" in INPUT_SYNTAX_PROMPT
    # "internal" secrecy signal is the whole point — must be present.
    assert "private" in INPUT_SYNTAX_PROMPT.lower()
