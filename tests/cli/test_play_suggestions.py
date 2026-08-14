"""End-to-end REPL tests for scene suggestions, running the CLI as a subprocess.

The `full-ok` fixture carries two static suggestions (a say + an action), so
with the offline Echo provider (whose replies never parse as S:/T:/A: lines)
every suggestion list is the static fallback — deterministic to assert on.

These subprocess runs are piped, i.e. non-TTY: the interactive arrow-key
selection can't engage, so the list is printed plainly and the typed `[N]` /
`:N` fallback path is what gets exercised here. The interactive path is
covered by the pty tests in tests/repl/test_lineedit.py.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
SRC = Path(__file__).resolve().parent.parent.parent / "src"

SAY_ROW = '[1] "Barkeep, what\'s the note about?"'
FREE_ROW = "[3] 说点什么…"


def _run(*args: str, home: Path, stdin: str | None = None, config_extra: str = ""):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC)
    env["NO_COLOR"] = "1"
    env["TAVERN_CONFIG_HOME"] = str(home)
    env.pop("XDG_CONFIG_HOME", None)
    home.mkdir(parents=True, exist_ok=True)
    (home / "config.toml").write_text(
        '[llm.default]\nprovider = "echo"\nmodel = ""\napi_key = ""\n' + config_extra,
        encoding="utf-8",
    )
    _run_install = subprocess.run(
        [sys.executable, "-m", "tavern", "install", "--force", str(FIXTURES / "full-ok")],
        capture_output=True, text=True, env=env,
    )
    assert _run_install.returncode == 0, _run_install.stderr
    return subprocess.run(
        [sys.executable, "-m", "tavern", *args],
        input=stdin,
        capture_output=True,
        text=True,
        env=env,
    )


def test_static_suggestions_list_shown_on_fresh_start(tmp_path: Path):
    p = _run("play", "full-ok", home=tmp_path / "home", stdin="/quit\n")
    assert p.returncode == 0
    assert SAY_ROW in p.stdout
    assert FREE_ROW in p.stdout


def test_select_say_suggestion_persists_quoted_raw(tmp_path: Path):
    home = tmp_path / "home"
    p = _run("play", "full-ok", home=home, stdin="[1]\n/quit\n")
    assert p.returncode == 0
    # The say suggestion reached the provider as a spoken line…
    assert 'Player says (aloud): "Barkeep, what\'s the note about?"' in p.stdout

    # …and the save holds the RAW quoted line, not "[1]" and not the
    # LLM-facing "Player says" framing.
    p2 = _run("play", "full-ok", home=home, stdin="/quit\n")
    assert '[player] "Barkeep, what\'s the note about?"' in p2.stdout
    assert "[player] [1]" not in p2.stdout


def test_select_action_suggestion_via_colon(tmp_path: Path):
    p = _run("play", "full-ok", home=tmp_path / "home", stdin=":2\n/quit\n")
    assert p.returncode == 0
    assert "Player does: Study the watcher at the far table" in p.stdout


def test_free_option_number_hands_back_to_typing(tmp_path: Path):
    # `[3]` is the "说点什么" tail — it must NOT reach the provider; the
    # next line the player types is what gets sent.
    p = _run(
        "play", "full-ok", home=tmp_path / "home",
        stdin="[3]\nhello there\n/quit\n",
    )
    assert p.returncode == 0
    assert "Player does: [3]" not in p.stdout
    assert "Player does: hello there" in p.stdout


def test_out_of_range_selection_rejected(tmp_path: Path):
    p = _run("play", "full-ok", home=tmp_path / "home", stdin="[9]\n/quit\n")
    assert p.returncode == 0
    assert "[no suggestion 9]" in p.stdout
    # Must NOT reach the provider as free text.
    assert "Player does: [9]" not in p.stdout


def test_free_input_still_first_class(tmp_path: Path):
    # Free-form typing is untouched by the suggestion machinery.
    p = _run("play", "full-ok", home=tmp_path / "home", stdin="walk to the bar\n/quit\n")
    assert "Player does: walk to the bar" in p.stdout


def test_hint_off_hides_list_after_turn(tmp_path: Path):
    p = _run(
        "play", "full-ok", home=tmp_path / "home",
        stdin="/hint off\nhello\n/quit\n",
    )
    # Only the initial turn-0 list appears; the "hello" turn adds none.
    assert p.stdout.count(SAY_ROW) == 1


def test_hint_on_reenables(tmp_path: Path):
    p = _run(
        "play", "full-ok", home=tmp_path / "home",
        stdin="/hint off\nhello\n/hint on\nworld\n/quit\n",
    )
    # initial list + list after /hint on + list after the "world" turn.
    assert p.stdout.count(SAY_ROW) == 3


def test_ui_suggestions_false_disables_at_boot(tmp_path: Path):
    p = _run(
        "play", "full-ok", home=tmp_path / "home",
        stdin="hello\n/quit\n",
        config_extra="\n[ui]\nsuggestions = false\n",
    )
    assert SAY_ROW not in p.stdout
    assert FREE_ROW not in p.stdout


def test_help_mentions_hint_and_selection(tmp_path: Path):
    p = _run("play", "full-ok", home=tmp_path / "home", stdin="/help\n/quit\n")
    assert "/hint" in p.stdout
    assert "↑/↓" in p.stdout
    assert "[1] [2] [3]" in p.stdout
