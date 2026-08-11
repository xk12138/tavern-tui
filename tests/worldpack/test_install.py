"""Tests for install / list / uninstall.

Every test runs with TAVERN_CONFIG_HOME pointing at a per-test tmp directory
(see `tavern_home` fixture in conftest.py) so nothing ever touches the real
user config.
"""

from __future__ import annotations

import tarfile
import zipfile
from pathlib import Path

import pytest

from tavern.worldpack.install import (
    INSTALLED_META,
    InstallError,
    install,
    list_installed,
    uninstall,
    worlds_dir,
)


# ── install: three source types ──────────────────────────────────────────


def test_install_single_toml(FIXTURES_DIR, tavern_home):
    installed = install(FIXTURES_DIR / "minimal-ok" / "world.toml")
    assert installed.id == "minimal-ok"
    assert installed.source_type == "file"
    assert (installed.path / "world.toml").is_file()
    # metadata written
    assert (installed.path / INSTALLED_META).is_file()


def test_install_directory(FIXTURES_DIR, tavern_home):
    installed = install(FIXTURES_DIR / "full-ok")
    assert installed.id == "full-ok"
    assert installed.source_type == "dir"
    # sub-files copied over
    assert (installed.path / "npcs" / "barkeep.toml").is_file()
    assert (installed.path / "templates" / "wanderer.toml").is_file()


def test_install_targz_archive(FIXTURES_DIR, tavern_home, tmp_path: Path):
    archive = tmp_path / "full-ok.tar.gz"
    src = FIXTURES_DIR / "full-ok"
    with tarfile.open(archive, "w:gz") as tf:
        tf.add(src, arcname="full-ok")

    installed = install(archive)
    assert installed.id == "full-ok"
    assert installed.source_type == "tar.gz"
    assert (installed.path / "npcs" / "barkeep.toml").is_file()


def test_install_zip_archive(FIXTURES_DIR, tavern_home, tmp_path: Path):
    archive = tmp_path / "minimal.zip"
    src = FIXTURES_DIR / "minimal-ok" / "world.toml"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.write(src, arcname="minimal-ok/world.toml")

    installed = install(archive)
    assert installed.id == "minimal-ok"
    assert installed.source_type == "zip"


# ── conflicts ────────────────────────────────────────────────────────────


def test_install_conflict_without_force(FIXTURES_DIR, tavern_home):
    install(FIXTURES_DIR / "minimal-ok" / "world.toml")
    with pytest.raises(InstallError) as exc:
        install(FIXTURES_DIR / "minimal-ok" / "world.toml")
    assert exc.value.code == "exists"


def test_install_force_overwrites(FIXTURES_DIR, tavern_home):
    first = install(FIXTURES_DIR / "minimal-ok" / "world.toml")
    (first.path / "sentinel.txt").write_text("stale")
    second = install(FIXTURES_DIR / "minimal-ok" / "world.toml", force=True)
    assert second.id == first.id
    # force must remove the previous directory entirely, taking sentinel with it
    assert not (second.path / "sentinel.txt").exists()


# ── validation gating ────────────────────────────────────────────────────


def test_install_rejects_invalid_pack(FIXTURES_DIR, tavern_home):
    with pytest.raises(InstallError) as exc:
        install(FIXTURES_DIR / "missing-required" / "world.toml")
    assert exc.value.code == "validation"


def test_install_force_bypasses_validation(FIXTURES_DIR, tavern_home):
    installed = install(FIXTURES_DIR / "missing-required" / "world.toml", force=True)
    assert installed.id == "missing-required"


def test_install_skip_validate(FIXTURES_DIR, tavern_home):
    installed = install(
        FIXTURES_DIR / "missing-required" / "world.toml",
        skip_validate=True,
    )
    assert installed.id == "missing-required"


# ── security: zip slip ───────────────────────────────────────────────────


def test_install_rejects_zip_slip(tavern_home, tmp_path: Path):
    archive = tmp_path / "evil.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        # would extract to ../pwned outside the staging dir
        zf.writestr("../pwned.toml", "[world]\nid='pwn'\nname='p'\n")
    with pytest.raises(InstallError) as exc:
        install(archive)
    assert exc.value.code == "bad_archive"


def test_install_rejects_absolute_path_member(tavern_home, tmp_path: Path):
    archive = tmp_path / "evil.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("/abs/world.toml", "[world]\nid='pwn'\nname='p'\n")
    with pytest.raises(InstallError) as exc:
        install(archive)
    assert exc.value.code == "bad_archive"


def test_install_rejects_unsupported_source(tavern_home, tmp_path: Path):
    weird = tmp_path / "not-a-worldpack.txt"
    weird.write_text("hello")
    with pytest.raises(InstallError) as exc:
        install(weird)
    assert exc.value.code == "bad_archive"


def test_install_missing_source(tavern_home, tmp_path: Path):
    with pytest.raises(InstallError) as exc:
        install(tmp_path / "does-not-exist")
    assert exc.value.code == "not_found"


# ── list ─────────────────────────────────────────────────────────────────


def test_list_empty(tavern_home):
    assert list_installed() == []


def test_list_returns_installed_worlds(FIXTURES_DIR, tavern_home):
    install(FIXTURES_DIR / "minimal-ok" / "world.toml")
    install(FIXTURES_DIR / "full-ok")

    listed = list_installed()
    ids = [w.id for w in listed]
    assert set(ids) == {"minimal-ok", "full-ok"}
    # sorted for stable output
    assert ids == sorted(ids)


def test_list_skips_junk_dirs(FIXTURES_DIR, tavern_home):
    install(FIXTURES_DIR / "minimal-ok" / "world.toml")
    # Sibling directory that isn't a worldpack
    (worlds_dir() / "not-a-world").mkdir()

    listed = list_installed()
    assert [w.id for w in listed] == ["minimal-ok"]


# ── uninstall ────────────────────────────────────────────────────────────


def test_uninstall_removes_directory(FIXTURES_DIR, tavern_home):
    installed = install(FIXTURES_DIR / "minimal-ok" / "world.toml")
    assert installed.path.exists()

    snapshot = uninstall("minimal-ok")
    assert snapshot.id == "minimal-ok"
    assert not installed.path.exists()
    assert list_installed() == []


def test_uninstall_missing_world(tavern_home):
    with pytest.raises(InstallError) as exc:
        uninstall("nope")
    assert exc.value.code == "not_found"


# ── metadata roundtrip ───────────────────────────────────────────────────


def test_install_metadata_is_written_and_readable(FIXTURES_DIR, tavern_home):
    installed = install(FIXTURES_DIR / "minimal-ok" / "world.toml")
    listed = list_installed()
    assert len(listed) == 1
    got = listed[0]
    assert got.source_type == "file"
    # source is stored as an absolute path
    assert Path(got.source).is_absolute()
    assert got.installed_at.endswith("Z")
