"""End-to-end CLI tests: invoke `python -m tavern validate ...` in a subprocess.

We don't try to test the CLI's fancy ANSI output — that's for humans. Here
we're only about exit codes and mechanically-checkable strings.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
SRC = Path(__file__).resolve().parent.parent.parent / "src"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC)
    env["NO_COLOR"] = "1"  # keep output easy to assert against
    return subprocess.run(
        [sys.executable, "-m", "tavern", *args],
        capture_output=True,
        text=True,
        env=env,
    )


def test_validate_ok_returns_zero():
    proc = _run("validate", str(FIXTURES / "full-ok"))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Validation passed" in proc.stdout


def test_validate_broken_returns_one():
    proc = _run("validate", str(FIXTURES / "broken-toml" / "world.toml"))
    assert proc.returncode == 1
    assert "Validation failed" in proc.stdout


def test_missing_path_returns_two(tmp_path: Path):
    proc = _run("validate", str(tmp_path / "does-not-exist"))
    assert proc.returncode == 2
    assert "does not exist" in proc.stderr


def test_strict_treats_warnings_as_failure():
    proc = _run("validate", "--strict", str(FIXTURES / "no-factions" / "world.toml"))
    assert proc.returncode == 1


def test_non_strict_ignores_warnings():
    proc = _run("validate", str(FIXTURES / "no-factions" / "world.toml"))
    assert proc.returncode == 0


def test_no_color_env_suppresses_ansi():
    proc = _run("validate", str(FIXTURES / "full-ok"))
    # With NO_COLOR the output should be free of ANSI escape sequences.
    assert "\x1b[" not in proc.stdout


def test_help_lists_validate_subcommand():
    proc = _run("--help")
    assert proc.returncode == 0
    assert "validate" in proc.stdout


def test_version_flag():
    proc = _run("--version")
    assert proc.returncode == 0
    assert "tavern" in proc.stdout
