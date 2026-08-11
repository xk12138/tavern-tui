"""End-to-end tests for `tavern install|list|uninstall`.

Runs the CLI as a subprocess with an isolated TAVERN_CONFIG_HOME so exit
codes and output are checked end-to-end.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
SRC = Path(__file__).resolve().parent.parent.parent / "src"


def _run(*args: str, home: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC)
    env["NO_COLOR"] = "1"
    env["TAVERN_CONFIG_HOME"] = str(home)
    env.pop("XDG_CONFIG_HOME", None)
    return subprocess.run(
        [sys.executable, "-m", "tavern", *args],
        capture_output=True,
        text=True,
        env=env,
    )


def test_install_then_list(tmp_path: Path):
    home = tmp_path / "home"
    p = _run("install", str(FIXTURES / "minimal-ok" / "world.toml"), home=home)
    assert p.returncode == 0, p.stdout + p.stderr
    assert "installed world 'minimal-ok'" in p.stdout

    p = _run("list", home=home)
    assert p.returncode == 0
    assert "minimal-ok" in p.stdout


def test_list_empty_message(tmp_path: Path):
    p = _run("list", home=tmp_path / "empty-home")
    assert p.returncode == 0
    assert "No worlds installed" in p.stdout


def test_list_long_shows_metadata(tmp_path: Path):
    home = tmp_path / "home"
    _run("install", str(FIXTURES / "full-ok"), home=home)
    p = _run("list", "--long", home=home)
    assert p.returncode == 0
    assert "source     :" in p.stdout
    assert "installed  :" in p.stdout


def test_install_conflict_exit_1(tmp_path: Path):
    home = tmp_path / "home"
    _run("install", str(FIXTURES / "minimal-ok" / "world.toml"), home=home)
    p = _run("install", str(FIXTURES / "minimal-ok" / "world.toml"), home=home)
    assert p.returncode == 1
    assert "already installed" in p.stderr


def test_install_force(tmp_path: Path):
    home = tmp_path / "home"
    _run("install", str(FIXTURES / "minimal-ok" / "world.toml"), home=home)
    p = _run(
        "install", "--force", str(FIXTURES / "minimal-ok" / "world.toml"),
        home=home,
    )
    assert p.returncode == 0


def test_install_invalid_pack_exit_1(tmp_path: Path):
    p = _run(
        "install", str(FIXTURES / "missing-required" / "world.toml"),
        home=tmp_path / "home",
    )
    assert p.returncode == 1
    assert "validation" in p.stderr


def test_uninstall_yes_flag(tmp_path: Path):
    home = tmp_path / "home"
    _run("install", str(FIXTURES / "minimal-ok" / "world.toml"), home=home)
    p = _run("uninstall", "minimal-ok", "--yes", home=home)
    assert p.returncode == 0
    assert "Removed" in p.stdout

    p = _run("list", home=home)
    assert "minimal-ok" not in p.stdout


def test_uninstall_missing_world_exit_1(tmp_path: Path):
    p = _run("uninstall", "nope", "--yes", home=tmp_path / "home")
    assert p.returncode == 1
    assert "no installed world" in p.stderr


def test_install_missing_source_exit_2(tmp_path: Path):
    p = _run("install", str(tmp_path / "nowhere"), home=tmp_path / "home")
    assert p.returncode == 2
