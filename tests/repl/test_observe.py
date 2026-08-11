"""Tests for observation renderers.

These are pure functions of (pack, save) → string. We build minimal packs
and saves in-memory rather than reaching for fixtures.

Security-critical test: `test_who_never_leaks_goals_or_secrets` guards the
NPC info boundary — goals and secrets are GM-side and must never appear in
`/who` output.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tavern.repl.observe import (
    render_inv,
    render_relations,
    render_status,
    render_where,
    render_who,
)
from tavern.save import Save
from tavern.worldpack.schema import NPC, World, WorldPack


def _pack(**over) -> WorldPack:
    world = World(
        id="w",
        name=over.get("name", "Test World"),
        initial_tavern=over.get("initial_tavern", {
            "name": "The Test Bar",
            "location": "Nowhere",
            "description": "A quiet room.\nDust hangs in the air.",
            "present_npcs": [],
        }),
    )
    npcs = over.get("npcs", {})
    return WorldPack(world=world, npcs=npcs)


def _shen_npc() -> NPC:
    """A realistic NPC with goals + secrets — used to test the security boundary."""
    return NPC(
        id="shen-shuoshu",
        name="沈先生",
        alias=["说书人", "沈老"],
        card={
            "appearance": "五十来岁,身材瘦长,右手食指有一道旧疤",
            "personality": "表面豁达实则谨慎",
            "speech_style": "半文半白,爱用典故",
            "goals": ["找到当年少林内乱中失踪的师弟"],
            "secrets": ["他其实是少林俗家弟子,当年内乱中背叛师门"],
        },
        initial_impression={
            "description": "醉仙楼的常客,自称说书人。",
        },
    )


# ── /where ──────────────────────────────────────────────────────────────


def test_where_uses_initial_tavern_when_no_current_scene(tavern_home):
    pack = _pack()
    with Save.new("s", world_id="w") as save:
        out = render_where(pack, save)
        assert "The Test Bar" in out
        assert "Nowhere" in out
        assert "A quiet room." in out
        # New save at turn 0 has no time_of_day set
        assert "(turn 0)" in out


def test_where_prefers_current_scene_from_state(tavern_home):
    pack = _pack()
    with Save.new("s", world_id="w") as save:
        save.update_state(current_scene="Elsewhere", turn_count=5)
        out = render_where(pack, save)
        assert "Elsewhere" in out
        # Should NOT fall back to initial_tavern details when state has a scene
        assert "The Test Bar" not in out


def test_where_missing_description_ok(tavern_home):
    pack = _pack(initial_tavern={"name": "Bare", "location": "here"})
    with Save.new("s", world_id="w") as save:
        out = render_where(pack, save)
        assert "Bare" in out


# ── /who list ───────────────────────────────────────────────────────────


def test_who_empty_scene(tavern_home):
    pack = _pack()
    with Save.new("s", world_id="w") as save:
        out = render_who(pack, save)
        assert "no npcs" in out.lower()


def test_who_lists_present_npcs(tavern_home):
    npc = _shen_npc()
    pack = _pack(
        initial_tavern={
            "name": "Tavern",
            "present_npcs": ["shen-shuoshu"],
        },
        npcs={"shen-shuoshu": npc},
    )
    with Save.new("s", world_id="w") as save:
        out = render_who(pack, save)
        assert "沈先生" in out
        assert "shen-shuoshu" in out
        assert "醉仙楼的常客" in out


def test_who_list_present_but_missing_from_npcs(tavern_home):
    """Referenced but not in pack.npcs — surface the id + a placeholder."""
    pack = _pack(
        initial_tavern={"name": "T", "present_npcs": ["ghost"]},
        npcs={},
    )
    with Save.new("s", world_id="w") as save:
        out = render_who(pack, save)
        assert "ghost" in out


# ── /who <name> ─────────────────────────────────────────────────────────


def test_who_find_by_id(tavern_home):
    pack = _pack(npcs={"shen-shuoshu": _shen_npc()})
    with Save.new("s", world_id="w") as save:
        out = render_who(pack, save, "shen-shuoshu")
        assert "沈先生" in out
        assert "Appearance:" in out


def test_who_find_by_name(tavern_home):
    pack = _pack(npcs={"shen-shuoshu": _shen_npc()})
    with Save.new("s", world_id="w") as save:
        out = render_who(pack, save, "沈先生")
        assert "shen-shuoshu" in out


def test_who_find_by_alias(tavern_home):
    pack = _pack(npcs={"shen-shuoshu": _shen_npc()})
    with Save.new("s", world_id="w") as save:
        out = render_who(pack, save, "说书人")
        assert "沈先生" in out


def test_who_find_case_insensitive(tavern_home):
    npc = NPC(id="alice", name="Alice", alias=[])
    pack = _pack(npcs={"alice": npc})
    with Save.new("s", world_id="w") as save:
        assert "Alice" in render_who(pack, save, "ALICE")
        assert "Alice" in render_who(pack, save, "alice")


def test_who_not_found(tavern_home):
    pack = _pack(npcs={"alice": NPC(id="alice", name="Alice")})
    with Save.new("s", world_id="w") as save:
        out = render_who(pack, save, "bob")
        assert "no such NPC" in out
        assert "bob" in out


# ── /who: SECURITY — no leaking of GM-side info ─────────────────────────


def test_who_never_leaks_goals_or_secrets(tavern_home):
    """Regression guard: /who is player-facing; goals/secrets are GM-side.

    Explicit test because a well-meaning refactor could easily 'improve' by
    dumping the whole card. That would spoil the story.
    """
    npc = _shen_npc()
    pack = _pack(npcs={"shen-shuoshu": npc})
    with Save.new("s", world_id="w") as save:
        out = render_who(pack, save, "shen-shuoshu")

        # concrete secret text — never in output
        assert "少林俗家弟子" not in out
        assert "背叛" not in out
        # concrete goal text — never in output
        assert "失踪的师弟" not in out
        # generic labels also not present
        assert "secret" not in out.lower()
        assert "goal" not in out.lower()


# ── /inv /status /relations ─────────────────────────────────────────────


def test_inv_shows_not_tracked(tavern_home):
    pack = _pack()
    with Save.new("s", world_id="w") as save:
        out = render_inv(pack, save)
        assert "not tracked" in out.lower()
        assert "Extractor" in out


def test_status_shows_available_fields(tavern_home):
    pack = _pack()
    with Save.new("s", world_id="w") as save:
        save.update_state(turn_count=7, day=2, current_scene="Elsewhere")
        out = render_status(pack, save)
        assert "turn:" in out
        assert "7" in out
        assert "Elsewhere" in out
        # But also states what's missing
        assert "HP" in out
        assert "tracked" in out.lower()


def test_relations_shows_not_tracked(tavern_home):
    pack = _pack()
    with Save.new("s", world_id="w") as save:
        out = render_relations(pack, save)
        assert "not tracked" in out.lower()
