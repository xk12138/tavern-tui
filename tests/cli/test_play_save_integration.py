"""End-to-end tests for `tavern play` with save persistence and `tavern saves`."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
SRC = Path(__file__).resolve().parent.parent.parent / "src"


def _run(*args: str, home: Path, stdin: str | None = None):
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


def _bootstrap(home: Path, world_src: Path = FIXTURES / "full-ok") -> None:
    home.mkdir(parents=True, exist_ok=True)
    (home / "config.toml").write_text(
        '[llm.default]\nprovider = "echo"\nmodel = ""\napi_key = ""\n',
        encoding="utf-8",
    )
    _run("install", str(world_src), home=home)


# ── persistence ──────────────────────────────────────────────────────────


def test_play_persists_across_sessions(tmp_path: Path):
    home = tmp_path / "home"
    _bootstrap(home)

    _run("play", "full-ok", home=home, stdin="one\ntwo\n/quit\n")
    p = _run("play", "full-ok", home=home, stdin="/quit\n")
    assert p.returncode == 0
    # continuation summary should mention 2 turns
    assert "continuing from turn 2" in p.stdout
    assert "[player] one" in p.stdout
    assert "[player] two" in p.stdout


def test_play_creates_default_save(tmp_path: Path):
    home = tmp_path / "home"
    _bootstrap(home)
    _run("play", "full-ok", home=home, stdin="hello\n/quit\n")

    saves_dir = home / "saves"
    assert saves_dir.is_dir()
    assert (saves_dir / "default-full-ok.db").is_file()


def test_play_new_flag_resets(tmp_path: Path):
    home = tmp_path / "home"
    _bootstrap(home)
    _run("play", "full-ok", home=home, stdin="first\n/quit\n")
    p = _run("play", "full-ok", "--new", home=home, stdin="/quit\n")
    assert p.returncode == 0
    assert "0 turns" in p.stdout    # header should show reset
    assert "continuing from" not in p.stdout


# ── slash commands ──────────────────────────────────────────────────────


def test_slash_help_prints_commands(tmp_path: Path):
    home = tmp_path / "home"
    _bootstrap(home)
    p = _run("play", "full-ok", home=home, stdin="/help\n/quit\n")
    assert "/save" in p.stdout
    assert "/load" in p.stdout
    assert "/saves" in p.stdout
    assert "/rewind" in p.stdout


def test_slash_saves_lists_saves(tmp_path: Path):
    home = tmp_path / "home"
    _bootstrap(home)
    p = _run(
        "play", "full-ok", home=home,
        stdin="thing\n/save keypoint\n/saves\n/quit\n",
    )
    assert "keypoint" in p.stdout
    assert "default-full-ok" in p.stdout


def test_slash_rewind_undoes_turn(tmp_path: Path):
    home = tmp_path / "home"
    _bootstrap(home)
    p = _run(
        "play", "full-ok", home=home,
        stdin="a\nb\n/rewind\n/quit\n",
    )
    assert "Rewound 1 turn" in p.stdout

    # persistence check
    p2 = _run("play", "full-ok", home=home, stdin="/quit\n")
    assert "continuing from turn 1" in p2.stdout


def test_slash_rewind_when_empty(tmp_path: Path):
    home = tmp_path / "home"
    _bootstrap(home)
    p = _run("play", "full-ok", home=home, stdin="/rewind\n/quit\n")
    assert "nothing to rewind" in p.stdout


def test_slash_load_bad_name(tmp_path: Path):
    home = tmp_path / "home"
    _bootstrap(home)
    p = _run(
        "play", "full-ok", home=home,
        stdin="/load ghost\n/quit\n",
    )
    assert "[error]" in p.stdout
    assert p.returncode == 0     # REPL survives


def test_slash_load_actually_switches(tmp_path: Path):
    home = tmp_path / "home"
    _bootstrap(home)
    _run("play", "full-ok", home=home,
         stdin="first\n/save snapshot\nsecond\n/quit\n")
    # Now default has 2 turns, snapshot has 1. Load snapshot.
    p = _run("play", "full-ok", home=home,
             stdin="/load snapshot\n/quit\n")
    assert "Loaded 'snapshot'" in p.stdout
    assert "turn 1" in p.stdout


def test_slash_unknown_command(tmp_path: Path):
    home = tmp_path / "home"
    _bootstrap(home)
    p = _run("play", "full-ok", home=home, stdin="/nope\n/quit\n")
    assert "unknown command" in p.stdout


# ── tavern saves top-level ───────────────────────────────────────────────


def test_saves_command_empty(tmp_path: Path):
    p = _run("saves", home=tmp_path / "home")
    assert p.returncode == 0
    assert "No saves yet" in p.stdout


def test_saves_command_lists(tmp_path: Path):
    home = tmp_path / "home"
    _bootstrap(home)
    _run("play", "full-ok", home=home, stdin="hi\n/quit\n")
    p = _run("saves", home=home)
    assert p.returncode == 0
    assert "default-full-ok" in p.stdout
    assert "full-ok" in p.stdout       # world column
    assert "TURNS" in p.stdout


def test_saves_command_long(tmp_path: Path):
    home = tmp_path / "home"
    _bootstrap(home)
    _run("play", "full-ok", home=home, stdin="hi\n/quit\n")
    p = _run("saves", "--long", home=home)
    assert ".db" in p.stdout          # path shown
