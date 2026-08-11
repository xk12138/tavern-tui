"""Tests for the export engine.

We use EchoProvider so tests run offline. Content shape (front matter,
intro, footer) is asserted rather than trying to test the LLM's output.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tavern.export import ExportError, export_novel
from tavern.export.novel import (
    _build_chunks,
    _last_paragraph,
    _pair_turns,
)
from tavern.llm.echo import EchoProvider
from tavern.save import Save
from tavern.save.store import Turn
from tavern.worldpack.loader import load_worldpack


@pytest.fixture
def novels_home(monkeypatch, tmp_path: Path) -> Path:
    """Isolate TAVERN_NOVELS_HOME to a per-test tmpdir."""
    home = tmp_path / "novels"
    monkeypatch.setenv("TAVERN_NOVELS_HOME", str(home))
    return home


# ── _pair_turns ──────────────────────────────────────────────────────────


def _turn(role: str, text: str, turn_no: int = 0) -> Turn:
    return Turn(id=0, turn_no=turn_no, role=role, text=text, created_at="")


def test_pair_turns_extracts_opening_and_pairs():
    turns = [
        _turn("system", "You enter."),
        _turn("player", "look", 1),
        _turn("gm", "You see stone.", 1),
        _turn("player", "walk", 2),
        _turn("gm", "You walk.", 2),
    ]
    opening, pairs = _pair_turns(turns)
    assert opening == "You enter."
    assert len(pairs) == 2
    assert pairs[0][0].text == "look"
    assert pairs[0][1].text == "You see stone."


def test_pair_turns_no_opening_when_no_system():
    turns = [_turn("player", "hi", 1), _turn("gm", "hi", 1)]
    opening, pairs = _pair_turns(turns)
    assert opening is None
    assert len(pairs) == 1


def test_pair_turns_only_first_system_is_opening():
    turns = [
        _turn("system", "first"),
        _turn("system", "second"),
        _turn("player", "p", 1),
        _turn("gm", "g", 1),
    ]
    opening, pairs = _pair_turns(turns)
    assert opening == "first"
    assert len(pairs) == 1


def test_pair_turns_skips_orphan_gm():
    turns = [_turn("gm", "orphan", 1)]
    opening, pairs = _pair_turns(turns)
    assert opening is None
    assert pairs == []


# ── _build_chunks ───────────────────────────────────────────────────────


def test_build_chunks_empty():
    assert _build_chunks([], threshold_chars=100) == []


def test_build_chunks_single_pair_under_threshold():
    pair = (_turn("player", "hi", 1), _turn("gm", "hi", 1))
    chunks = _build_chunks([pair], threshold_chars=1000)
    assert len(chunks) == 1
    assert len(chunks[0]) == 1


def test_build_chunks_splits_on_threshold():
    pairs = [
        (_turn("player", "a" * 200, i), _turn("gm", "b" * 200, i))
        for i in range(1, 6)
    ]
    # ~400 chars per pair, threshold 500 → each pair gets its own chunk
    chunks = _build_chunks(pairs, threshold_chars=500)
    assert len(chunks) == 5


def test_build_chunks_packs_within_threshold():
    pairs = [
        (_turn("player", "a" * 100, i), _turn("gm", "b" * 100, i))
        for i in range(1, 6)
    ]
    # ~200 chars per pair, threshold 1000 → 5 pairs fit in one chunk
    chunks = _build_chunks(pairs, threshold_chars=1000)
    assert len(chunks) == 1
    assert len(chunks[0]) == 5


# ── _last_paragraph ─────────────────────────────────────────────────────


def test_last_paragraph_empty():
    assert _last_paragraph("") == ""


def test_last_paragraph_single_para():
    assert _last_paragraph("just one paragraph") == "just one paragraph"


def test_last_paragraph_returns_final_after_blank_line():
    text = "first para\n\nsecond para\n\nthird para"
    assert _last_paragraph(text) == "third para"


def test_last_paragraph_truncates_long_tail():
    text = "x" * 500
    result = _last_paragraph(text, max_chars=100)
    assert len(result) == 100
    assert result == "x" * 100


# ── export_novel end-to-end (Echo) ──────────────────────────────────────


def test_export_novel_writes_file(tavern_home, novels_home):
    s = Save.new("run1", world_id="minimal-tavern")
    try:
        s.append_turn("system", "You enter a tavern.", turn_no=0)
        s.append_turn("player", "look", turn_no=1)
        s.append_turn("gm", "You see wood.", turn_no=1)
        s.update_state(turn_count=1)

        pack = load_worldpack("examples/minimal-tavern/world.toml").pack
        result = export_novel(s, pack, EchoProvider())

        assert result.output_path.is_file()
        assert result.turn_count == 1
        assert result.chunk_count == 1

        content = result.output_path.read_text(encoding="utf-8")
        # Front matter present
        assert content.startswith("---")
        assert "world:" in content
        assert 'save: "run1"' in content
        assert "turns: 1" in content
        # World name renders as heading
        assert "# 无名酒馆" in content
        # Footer
        assert "Tavern" in content
    finally:
        s.close()


def test_export_novel_raises_on_empty_save(tavern_home, novels_home):
    s = Save.new("empty", world_id="w")
    try:
        pack = load_worldpack("examples/minimal-tavern/world.toml").pack
        with pytest.raises(ExportError, match="no turns"):
            export_novel(s, pack, EchoProvider())
    finally:
        s.close()


def test_export_novel_refuses_existing_output(tavern_home, novels_home, tmp_path):
    s = Save.new("run", world_id="w")
    try:
        s.append_turn("player", "hi", turn_no=1)
        s.append_turn("gm", "hi", turn_no=1)
        s.update_state(turn_count=1)
        out = tmp_path / "already.md"
        out.write_text("stale")
        with pytest.raises(ExportError, match="already exists"):
            export_novel(s, None, EchoProvider(), output=out)
    finally:
        s.close()


def test_export_novel_force_overwrites(tavern_home, novels_home, tmp_path):
    s = Save.new("run", world_id="w")
    try:
        s.append_turn("player", "hi", turn_no=1)
        s.append_turn("gm", "hi", turn_no=1)
        s.update_state(turn_count=1)
        out = tmp_path / "already.md"
        out.write_text("stale")
        result = export_novel(
            s, None, EchoProvider(), output=out, force=True,
        )
        assert result.output_path == out
        assert out.read_text(encoding="utf-8") != "stale"
    finally:
        s.close()


def test_export_novel_without_world_pack(tavern_home, novels_home):
    s = Save.new("run", world_id="lost-world")
    try:
        s.append_turn("player", "hi", turn_no=1)
        s.append_turn("gm", "you're alone", turn_no=1)
        s.update_state(turn_count=1)

        result = export_novel(s, None, EchoProvider())
        content = result.output_path.read_text(encoding="utf-8")
        # Falls back to world_id as title.
        assert "lost-world" in content
    finally:
        s.close()


def test_export_novel_multiple_chunks(tavern_home, novels_home):
    """Force multi-chunk path by setting a low threshold."""
    s = Save.new("big", world_id="minimal-tavern")
    try:
        for i in range(1, 5):
            s.append_turn("player", "a" * 300, turn_no=i)
            s.append_turn("gm", "b" * 300, turn_no=i)
        s.update_state(turn_count=4)

        pack = load_worldpack("examples/minimal-tavern/world.toml").pack
        result = export_novel(
            s, pack, EchoProvider(), threshold_chars=500,
        )
        assert result.turn_count == 4
        assert result.chunk_count > 1
        assert result.output_path.is_file()
    finally:
        s.close()


def test_export_novel_preserves_save(tavern_home, novels_home):
    """Export must be read-only w.r.t. the save."""
    s = Save.new("keep", world_id="minimal-tavern")
    try:
        s.append_turn("system", "opening", turn_no=0)
        s.append_turn("player", "hi", turn_no=1)
        s.append_turn("gm", "hi back", turn_no=1)
        s.update_state(turn_count=1)

        turns_before = len(s.turns())
        state_before = s.state

        pack = load_worldpack("examples/minimal-tavern/world.toml").pack
        export_novel(s, pack, EchoProvider())

        assert len(s.turns()) == turns_before
        assert s.state.turn_count == state_before.turn_count
    finally:
        s.close()
