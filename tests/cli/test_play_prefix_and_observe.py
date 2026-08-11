"""End-to-end REPL tests: prefix parsing + observe commands, running the CLI as a subprocess."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
SRC = Path(__file__).resolve().parent.parent.parent / "src"
EXAMPLES = Path(__file__).resolve().parent.parent.parent / "examples"


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


# ── prefix parsing plumbed through the REPL ─────────────────────────────


def test_say_prefix_reaches_provider_and_saves_raw(tmp_path: Path):
    home = tmp_path / "home"
    _bootstrap(home)

    p = _run("play", "full-ok", home=home, stdin='"hello there"\n/quit\n')
    assert p.returncode == 0
    # Echo provider echoes the LLM-facing line back to us — this proves
    # the say-prefix was translated on the way IN to the provider.
    assert 'Player says (aloud): "hello there"' in p.stdout

    # Resume and check the persisted transcript stores the RAW input,
    # not the LLM-facing line — the "[player]" line in the resume summary
    # should show `"hello there"` (quoted), not `Player says (aloud):`.
    p2 = _run("play", "full-ok", home=home, stdin="/quit\n")
    assert '[player] "hello there"' in p2.stdout
    # And the raw player line does NOT begin with "Player says" —
    # scan for the exact "[player] Player says" phrase, which would only
    # appear if we mistakenly persisted the llm_line.
    assert "[player] Player says" not in p2.stdout


def test_think_prefix_translates(tmp_path: Path):
    home = tmp_path / "home"
    _bootstrap(home)
    p = _run("play", "full-ok", home=home, stdin="*i don't trust her*\n/quit\n")
    assert p.returncode == 0
    assert "internal, unheard by others" in p.stdout


def test_shortcut_known(tmp_path: Path):
    home = tmp_path / "home"
    _bootstrap(home)
    p = _run("play", "full-ok", home=home, stdin=":look\n/quit\n")
    assert "Player quickly does: looks around" in p.stdout


def test_shortcut_unknown_passthrough(tmp_path: Path):
    home = tmp_path / "home"
    _bootstrap(home)
    p = _run("play", "full-ok", home=home, stdin=":ponder\n/quit\n")
    assert "Player quickly does: ponder" in p.stdout


def test_free_action_default(tmp_path: Path):
    home = tmp_path / "home"
    _bootstrap(home)
    p = _run("play", "full-ok", home=home, stdin="walk to the bar\n/quit\n")
    assert "Player does: walk to the bar" in p.stdout


# ── observe commands ────────────────────────────────────────────────────


def test_where_prints_initial_tavern(tmp_path: Path):
    home = tmp_path / "home"
    # Use the richer example world so the tavern has description.
    _bootstrap(home, world_src=EXAMPLES / "example-jianghu")
    p = _run(
        "play", "example-jianghu", home=home,
        stdin="/where\n/quit\n",
    )
    assert p.returncode == 0
    assert "醉仙楼" in p.stdout
    assert "洛阳" in p.stdout


def test_who_lists_and_details(tmp_path: Path):
    home = tmp_path / "home"
    _bootstrap(home, world_src=EXAMPLES / "example-jianghu")

    # List
    p = _run(
        "play", "example-jianghu", home=home,
        stdin="/who\n/quit\n",
    )
    assert "shen-shuoshu" in p.stdout

    # Details — must not leak secrets/goals
    p = _run(
        "play", "example-jianghu", home=home,
        stdin="/who shen-shuoshu\n/quit\n",
    )
    assert "沈先生" in p.stdout
    assert "五十来岁" in p.stdout           # appearance is public
    assert "背叛" not in p.stdout           # secret text must not leak
    assert "失踪的师弟" not in p.stdout      # goal text must not leak


def test_who_unknown(tmp_path: Path):
    home = tmp_path / "home"
    _bootstrap(home, world_src=EXAMPLES / "example-jianghu")
    p = _run("play", "example-jianghu", home=home, stdin="/who ghost\n/quit\n")
    assert p.returncode == 0
    assert "no such NPC" in p.stdout


def test_inv_status_relations_not_tracked(tmp_path: Path):
    home = tmp_path / "home"
    _bootstrap(home)
    p = _run(
        "play", "full-ok", home=home,
        stdin="/inv\n/status\n/relations\n/quit\n",
    )
    text = p.stdout.lower()
    # /inv and /relations use exactly "not tracked yet"; /status uses "tracked yet"
    # after "aren't". Assert on the common substring.
    assert text.count("tracked yet") >= 3


def test_help_shows_input_syntax(tmp_path: Path):
    home = tmp_path / "home"
    _bootstrap(home)
    p = _run("play", "full-ok", home=home, stdin="/help\n/quit\n")
    assert "Input syntax:" in p.stdout
    assert '"..."' in p.stdout
    assert "*...*" in p.stdout
    assert "/where" in p.stdout
    assert "/who" in p.stdout
