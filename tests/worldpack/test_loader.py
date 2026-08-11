"""Tests for the loader.

Loader tests focus on file-layout concerns (paths, missing files, TOML
parsing, id ↔ filename matching). Semantic checks live in
test_validator.py.
"""

from pathlib import Path

from tavern.worldpack.loader import load_worldpack


def test_load_missing_path(tmp_path):
    result = load_worldpack(tmp_path / "nope")
    assert result.pack is None
    assert any(e.code == "E001" for e in result.errors)


def test_load_directory_without_world_toml(tmp_path):
    result = load_worldpack(tmp_path)
    assert result.pack is None
    assert any(e.code == "E002" for e in result.errors)


def test_load_broken_toml(FIXTURES_DIR):
    result = load_worldpack(FIXTURES_DIR / "broken-toml" / "world.toml")
    assert result.pack is None
    assert any(e.code == "E003" for e in result.errors)


def test_load_minimal_ok(FIXTURES_DIR):
    result = load_worldpack(FIXTURES_DIR / "minimal-ok" / "world.toml")
    assert result.pack is not None
    assert result.pack.world.id == "minimal-ok"
    assert result.pack.world.name == "Minimal OK"
    # No npcs / templates for single-file mode
    assert result.pack.npcs == {}
    assert result.pack.templates == {}


def test_load_full_directory(FIXTURES_DIR):
    result = load_worldpack(FIXTURES_DIR / "full-ok")
    assert result.pack is not None
    pack = result.pack
    assert pack.world.id == "full-ok"
    assert "barkeep" in pack.npcs
    assert "wanderer" in pack.templates
    assert pack.intro is not None and pack.intro.startswith("#")


def test_npc_filename_must_match_id(tmp_path: Path):
    (tmp_path / "npcs").mkdir()
    (tmp_path / "world.toml").write_text(
        '[world]\nid="mismatch"\nname="Mismatch"\nversion="0.1.0"\n'
        '[world.setting]\nera="x"\ntone="x"\n'
        '[world.initial_tavern]\nname="a"\nlocation="b"\n'
        'description="c"\nopening_hook="' + "hook " * 20 + '"\n',
        encoding="utf-8",
    )
    (tmp_path / "npcs" / "wrongname.toml").write_text(
        '[npc]\nid="right"\nname="Right"\n', encoding="utf-8"
    )
    result = load_worldpack(tmp_path)
    assert any(e.code == "E008" for e in result.errors)


def test_duplicate_npc_ids(tmp_path: Path):
    (tmp_path / "npcs").mkdir()
    (tmp_path / "world.toml").write_text(
        '[world]\nid="dup"\nname="Dup"\nversion="0.1.0"\n'
        '[world.setting]\nera="x"\ntone="x"\n'
        '[world.initial_tavern]\nname="a"\nlocation="b"\n'
        'description="c"\nopening_hook="' + "hook " * 20 + '"\n',
        encoding="utf-8",
    )
    # Second file has matching stem "b" but writes the same id as "a.toml".
    (tmp_path / "npcs" / "a.toml").write_text(
        '[npc]\nid="a"\nname="Alice"\n', encoding="utf-8"
    )
    (tmp_path / "npcs" / "b.toml").write_text(
        '[npc]\nid="a"\nname="Duplicate"\n', encoding="utf-8"
    )
    result = load_worldpack(tmp_path)
    # E008 for filename mismatch on b.toml AND E009 for duplicate id.
    codes = {e.code for e in result.errors}
    assert "E009" in codes


