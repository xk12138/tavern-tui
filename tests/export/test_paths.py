"""Test path helpers for the export module."""

from __future__ import annotations

import datetime as _dt
from pathlib import Path

import pytest

from tavern.export.paths import default_output_path, novels_home


def test_novels_home_default(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("TAVERN_NOVELS_HOME", raising=False)
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    assert novels_home() == tmp_path / "tavern-novels"


def test_novels_home_env_override(monkeypatch, tmp_path: Path):
    override = tmp_path / "custom-novels"
    monkeypatch.setenv("TAVERN_NOVELS_HOME", str(override))
    assert novels_home() == override


def test_default_output_path_contains_name_and_timestamp(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("TAVERN_NOVELS_HOME", str(tmp_path))
    now = _dt.datetime(2026, 8, 11, 15, 47, 3, tzinfo=_dt.timezone.utc)
    p = default_output_path("my-run", now=now)
    assert p.parent == tmp_path
    assert p.name == "my-run-20260811-154703.md"


def test_default_output_path_sanitises_bad_chars(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("TAVERN_NOVELS_HOME", str(tmp_path))
    now = _dt.datetime(2026, 8, 11, 15, 47, 3, tzinfo=_dt.timezone.utc)
    p = default_output_path("bad/name with spaces", now=now)
    # Slashes and spaces should be replaced with underscores.
    assert "/" not in p.name
    assert " " not in p.name
