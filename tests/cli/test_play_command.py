"""End-to-end tests for `tavern play <world-id>`.

Uses EchoProvider so no network access is required. Runs the CLI as a
subprocess with an isolated TAVERN_CONFIG_HOME.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
SRC = Path(__file__).resolve().parent.parent.parent / "src"


def _run(
    *args: str,
    home: Path,
    stdin: str | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC)
    env["NO_COLOR"] = "1"
    env["TAVERN_CONFIG_HOME"] = str(home)
    env.pop("XDG_CONFIG_HOME", None)
    return subprocess.run(
        [sys.executable, "-m", "tavern", *args],
        input=stdin,
        capture_output=True,
        text=True,
        env=env,
    )


def _bootstrap(home: Path, world_src: Path) -> None:
    """Install a world and write an echo-provider config."""
    home.mkdir(parents=True, exist_ok=True)
    (home / "config.toml").write_text(
        '[llm.default]\nprovider = "echo"\nmodel = ""\napi_key = ""\n',
        encoding="utf-8",
    )
    _run("install", str(world_src), home=home)


# ── happy paths ──────────────────────────────────────────────────────────


def test_play_one_input_then_quit(tmp_path: Path):
    home = tmp_path / "home"
    _bootstrap(home, FIXTURES / "full-ok")
    p = _run("play", "full-ok", home=home, stdin="look around\n/quit\n")
    assert p.returncode == 0, p.stdout + p.stderr
    assert "[echo]" in p.stdout
    assert "look around" in p.stdout
    assert "Goodbye" in p.stdout


def test_play_eof_exits_cleanly(tmp_path: Path):
    home = tmp_path / "home"
    _bootstrap(home, FIXTURES / "full-ok")
    p = _run("play", "full-ok", home=home, stdin="")
    assert p.returncode == 0
    assert "Goodbye" in p.stdout


def test_play_prints_opening_hook(tmp_path: Path):
    home = tmp_path / "home"
    _bootstrap(home, FIXTURES / "full-ok")
    p = _run("play", "full-ok", home=home, stdin="/quit\n")
    # full-ok fixture's opening_hook mentions "barkeep"
    assert "barkeep" in p.stdout


def test_play_shows_provider(tmp_path: Path):
    home = tmp_path / "home"
    _bootstrap(home, FIXTURES / "full-ok")
    p = _run("play", "full-ok", home=home, stdin="/quit\n")
    assert "Echo" in p.stdout


def test_play_empty_line_skipped(tmp_path: Path):
    home = tmp_path / "home"
    _bootstrap(home, FIXTURES / "full-ok")
    # Send blank line then a real one — should only get one echo response
    p = _run(
        "play", "full-ok", home=home,
        stdin="\n\nsomething real\n/quit\n",
    )
    assert p.returncode == 0
    # Only "something real" produces an echo line
    assert p.stdout.count("[echo]") == 1
    assert "something real" in p.stdout


# ── error paths ──────────────────────────────────────────────────────────


def test_play_unknown_world(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    (home / "config.toml").write_text(
        '[llm.default]\nprovider = "echo"\nmodel = ""\napi_key = ""\n',
        encoding="utf-8",
    )
    p = _run("play", "nonexistent", home=home, stdin="/quit\n")
    assert p.returncode == 1
    assert "not installed" in p.stderr


def test_play_no_config(tmp_path: Path):
    home = tmp_path / "home"
    _bootstrap(home, FIXTURES / "full-ok")
    # Nuke config after install to simulate "no config"
    (home / "config.toml").unlink()
    p = _run("play", "full-ok", home=home, stdin="/quit\n")
    assert p.returncode == 1
    assert "config init" in p.stderr


def test_play_bad_provider_in_config(tmp_path: Path):
    home = tmp_path / "home"
    _bootstrap(home, FIXTURES / "full-ok")
    (home / "config.toml").write_text(
        '[llm.default]\nprovider = "bogus"\nmodel = ""\napi_key = ""\n',
        encoding="utf-8",
    )
    p = _run("play", "full-ok", home=home, stdin="/quit\n")
    assert p.returncode == 1
    assert "unknown provider" in p.stderr


def test_play_help_lists_command(tmp_path: Path):
    p = _run("play", "--help", home=tmp_path)
    assert p.returncode == 0
    assert "world_id" in p.stdout
