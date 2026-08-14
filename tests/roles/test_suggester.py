"""suggester: prompt shape, line parsing, merge, fallback, raw round-trip."""

from __future__ import annotations

from tavern.llm.base import LLMAuthError
from tavern.llm.echo import EchoProvider
from tavern.roles.suggester import (
    Suggestion,
    static_suggestions,
    suggest,
    suggestion_to_raw,
)
from tavern.worldpack.loader import load_worldpack


class FakeProvider:
    """Provider whose reply we control; records the system prompt it got."""

    def __init__(self, reply: str = ""):
        self.reply = reply
        self.last_system = ""
        self.last_user = ""

    def complete(self, prompt, *, system="", max_tokens=1024):
        self.last_system = system
        self.last_user = prompt if isinstance(prompt, str) else str(prompt)
        return self.reply

    def stream(self, prompt, **opts):
        yield self.complete(prompt, **opts)

    def describe(self) -> str:
        return "fake"


class BoomProvider:
    """Provider that always fails — suggest() must fall back to static."""

    def complete(self, prompt, *, system="", max_tokens=1024):
        raise LLMAuthError("boom")

    def stream(self, prompt, **opts):
        yield from ()

    def describe(self) -> str:
        return "boom"


class CrashProvider:
    """Provider that raises something outside the LLMError family — the
    "never raises" guarantee must hold for arbitrary provider bugs too."""

    def complete(self, prompt, *, system="", max_tokens=1024):
        raise RuntimeError("provider library bug")

    def stream(self, prompt, **opts):
        yield from ()

    def describe(self) -> str:
        return "crash"


class CapProvider:
    """Provider that rejects large max_tokens (like gpt-4o's 16k cap) but
    works with a conservative budget — exercises the degrade-and-retry."""

    def __init__(self):
        self.calls: list[int] = []

    def complete(self, prompt, *, system="", max_tokens=1024):
        self.calls.append(max_tokens)
        if max_tokens > 4096:
            raise LLMAuthError("max_tokens exceeds endpoint cap")
        return 'S: "one round"\nA: wave at the barkeep\n'

    def stream(self, prompt, **opts):
        yield from ()

    def describe(self) -> str:
        return "cap"


def _pack(FIXTURES_DIR):
    return load_worldpack(FIXTURES_DIR / "full-ok").pack


def _save_with_turns(FIXTURES_DIR, tmp_path, monkeypatch):
    from tavern.config import tavern_home
    monkeypatch.setenv("TAVERN_CONFIG_HOME", str(tmp_path / "home"))
    from tavern.save import Save
    save = Save.new("s1", world_id="full-ok")
    save.append_turn("player", "hello", turn_no=1)
    save.append_turn("gm", "The barkeep nods at you.", turn_no=1)
    return save


# ── static extraction ─────────────────────────────────────────────────────


def test_static_suggestions_parses_full_ok(FIXTURES_DIR):
    s = static_suggestions(_pack(FIXTURES_DIR))
    assert len(s) == 2
    assert s[0] == Suggestion(kind="say", text="Barkeep, what's the note about?")
    assert s[1].kind == "action"


def test_static_suggestions_skips_invalid(FIXTURES_DIR, tmp_path):
    (tmp_path / "world.toml").write_text(
        '[world]\nid="w"\nname="W"\nversion="0.1.0"\n'
        '[world.setting]\nera="x"\ntone="x"\n'
        '[world.initial_tavern]\nname="a"\nlocation="b"\n'
        'description="c"\nopening_hook="' + "hook " * 20 + '"\n'
        '[[world.initial_tavern.suggestions]]\nkind="shout"\ntext="hi"\n'
        '[[world.initial_tavern.suggestions]]\nkind="say"\ntext=""\n'
        '[[world.initial_tavern.suggestions]]\nkind="think"\ntext="*what is going on*"\n',
        encoding="utf-8",
    )
    s = static_suggestions(load_worldpack(tmp_path / "world.toml").pack)
    assert len(s) == 1
    assert s[0] == Suggestion(kind="think", text="*what is going on*")


def test_static_suggestions_none(FIXTURES_DIR):
    assert static_suggestions(load_worldpack(FIXTURES_DIR / "minimal-ok").pack) == []


# ── LLM line parsing & merge ──────────────────────────────────────────────


def test_suggest_parses_say_think_action_lines(FIXTURES_DIR, tmp_path, monkeypatch):
    prov = FakeProvider(
        reply='S: "Barkeep, one more round."\n'
        "A: examine the note under the candle\n"
        "T: *this whole town smells wrong*\n"
        "garbage line that must be dropped\n"
    )
    out = suggest(prov, _pack(FIXTURES_DIR), _save_with_turns(FIXTURES_DIR, tmp_path, monkeypatch))
    assert out == [
        Suggestion(kind="say", text="Barkeep, one more round."),
        Suggestion(kind="action", text="examine the note under the candle"),
        Suggestion(kind="think", text="this whole town smells wrong"),
    ]


def test_suggest_strips_extra_wrapping(FIXTURES_DIR, tmp_path, monkeypatch):
    prov = FakeProvider(reply='S: "quoted already"\nA: *not a thought*\n')
    out = suggest(prov, _pack(FIXTURES_DIR), _save_with_turns(FIXTURES_DIR, tmp_path, monkeypatch))
    # Wrapping quotes are stripped for storage; kind stays as declared.
    assert out[0] == Suggestion(kind="say", text="quoted already")
    assert out[1] == Suggestion(kind="action", text="not a thought")


def test_suggest_drops_overlong_lines(FIXTURES_DIR, tmp_path, monkeypatch):
    prov = FakeProvider(reply=f"A: {'x' * 300}\nS: ok\n")
    out = suggest(prov, _pack(FIXTURES_DIR), _save_with_turns(FIXTURES_DIR, tmp_path, monkeypatch))
    assert len(out) == 1
    assert out[0].kind == "say"


def test_suggest_static_first_then_dedupe_cap(FIXTURES_DIR, tmp_path, monkeypatch):
    static = [
        Suggestion(kind="say", text="Static one"),
        Suggestion(kind="action", text="dupe"),
    ]
    prov = FakeProvider(reply='S: "Static one"\nA: dupe\nS: "Fresh dynamic"\n')
    out = suggest(
        prov, _pack(FIXTURES_DIR), _save_with_turns(FIXTURES_DIR, tmp_path, monkeypatch),
        static=static, max_n=3,
    )
    assert [s.text for s in out] == ["Static one", "dupe", "Fresh dynamic"]


def test_suggest_max_n_truncates(FIXTURES_DIR, tmp_path, monkeypatch):
    prov = FakeProvider(reply='S: "1"\nS: "2"\nS: "3"\nS: "4"\n')
    out = suggest(prov, _pack(FIXTURES_DIR), _save_with_turns(FIXTURES_DIR, tmp_path, monkeypatch), max_n=3)
    assert len(out) == 3


def test_suggest_provider_failure_falls_back_to_static(FIXTURES_DIR, tmp_path, monkeypatch):
    static = [Suggestion(kind="say", text="Keep this")]
    out = suggest(
        BoomProvider(), _pack(FIXTURES_DIR),
        _save_with_turns(FIXTURES_DIR, tmp_path, monkeypatch),
        static=static,
    )
    assert out == static


def test_suggest_never_raises_on_arbitrary_provider_bug(FIXTURES_DIR, tmp_path, monkeypatch):
    out = suggest(
        CrashProvider(), _pack(FIXTURES_DIR),
        _save_with_turns(FIXTURES_DIR, tmp_path, monkeypatch),
        static=[],
    )
    assert out == []


def test_suggest_retries_with_smaller_max_tokens_when_capped(
    FIXTURES_DIR, tmp_path, monkeypatch
):
    """32768 is rejected by capped endpoints (gpt-4o/DeepSeek chat/Opus);
    the retry at 4096 must still produce suggestions."""
    prov = CapProvider()
    out = suggest(
        prov, _pack(FIXTURES_DIR),
        _save_with_turns(FIXTURES_DIR, tmp_path, monkeypatch),
        static=[],
    )
    assert prov.calls == [32768, 4096]
    assert [s.kind for s in out] == ["say", "action"]


def test_suggest_no_static_no_parse_returns_empty(FIXTURES_DIR, tmp_path, monkeypatch):
    out = suggest(
        EchoProvider(), _pack(FIXTURES_DIR),
        _save_with_turns(FIXTURES_DIR, tmp_path, monkeypatch),
        static=[],
    )
    # Echo echoes the trailing prompt line — nothing S:/T:/A:-shaped parses.
    assert out == []


def test_suggest_prompt_is_first_person_and_mentions_scene(FIXTURES_DIR, tmp_path, monkeypatch):
    prov = FakeProvider(reply='A: wave at the barkeep\n')
    suggest(prov, _pack(FIXTURES_DIR), _save_with_turns(FIXTURES_DIR, tmp_path, monkeypatch))
    assert "first-person" in prov.last_system
    assert "The barkeep nods at you." in prov.last_system  # scene context
    assert "hello" in prov.last_system  # player style reference


def test_suggest_seeds_from_opening_hook_before_any_turn(FIXTURES_DIR, tmp_path, monkeypatch):
    """Fresh game (turn 0): no GM rows yet, so the suggester must read the
    world's opening_hook — that's what lets the first prompt carry a real
    LLM recommendation instead of nothing."""
    from tavern.save import Save
    monkeypatch.setenv("TAVERN_CONFIG_HOME", str(tmp_path / "home"))
    save = Save.new("s0", world_id="full-ok")
    try:
        save.append_turn(
            "system",
            "The barkeep slides a note across the counter without meeting your eye.",
            turn_no=0,
        )
        prov = FakeProvider(reply='A: wave at the barkeep\n')
        suggest(prov, _pack(FIXTURES_DIR), save)
        assert "(opening scene)" in prov.last_system
        assert "The barkeep slides a note across the counter" in prov.last_system
    finally:
        save.close()


# ── raw round-trip & rendering ────────────────────────────────────────────


def test_suggestion_to_raw_and_parse_round_trip(FIXTURES_DIR):
    from tavern.repl.parser import parse_input

    for kind, text, expect_raw, expect_kind in [
        ("say", "Barkeep, one round", '"Barkeep, one round"', "say"),
        ("think", "it is a trap", "*it is a trap*", "think"),
        ("action", "examine the note", "examine the note", "action"),
    ]:
        s = Suggestion(kind=kind, text=text)
        raw = suggestion_to_raw(s)
        assert raw == expect_raw
        assert parse_input(raw).kind == expect_kind
