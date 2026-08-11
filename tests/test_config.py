"""Tests for tavern.config filesystem-layout resolution.

These are pure-logic tests: we only manipulate env vars and check the
returned Paths — no directories are actually created.
"""

from __future__ import annotations

from pathlib import Path

from tavern import config


def test_default_home_under_dot_config(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("TAVERN_CONFIG_HOME", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    fake_home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))

    assert config.tavern_home() == fake_home / ".config" / "tavern"
    assert config.worlds_dir() == fake_home / ".config" / "tavern" / "worlds"


def test_tavern_env_wins(monkeypatch, tmp_path: Path) -> None:
    override = tmp_path / "custom"
    monkeypatch.setenv("TAVERN_CONFIG_HOME", str(override))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    assert config.tavern_home() == override


def test_xdg_env_used_when_no_tavern_override(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("TAVERN_CONFIG_HOME", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    assert config.tavern_home() == tmp_path / "xdg" / "tavern"


def test_ensure_dirs_creates_worlds_dir(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("TAVERN_CONFIG_HOME", str(tmp_path / "home"))
    config.ensure_dirs()
    assert (tmp_path / "home" / "worlds").is_dir()
