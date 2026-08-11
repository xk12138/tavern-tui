"""End-to-end CLI tests for `tavern config init|show|check|path`."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent.parent / "src"


def _run(*args: str, home: Path, env_extra: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC)
    env["NO_COLOR"] = "1"
    env["TAVERN_CONFIG_HOME"] = str(home)
    env.pop("XDG_CONFIG_HOME", None)
    # Drop LLM keys that might leak in from the developer environment.
    for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "DEEPSEEK_API_KEY"):
        env.pop(k, None)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, "-m", "tavern", *args],
        capture_output=True,
        text=True,
        env=env,
    )


def _write_cfg(home: Path, body: str) -> None:
    home.mkdir(parents=True, exist_ok=True)
    (home / "config.toml").write_text(body, encoding="utf-8")


# ── path ─────────────────────────────────────────────────────────────────


def test_config_path_prints_absolute(tmp_path: Path):
    home = tmp_path / "home"
    p = _run("config", "path", home=home)
    assert p.returncode == 0
    assert p.stdout.strip() == str(home / "config.toml")


# ── show ─────────────────────────────────────────────────────────────────


def test_config_show_when_missing(tmp_path: Path):
    p = _run("config", "show", home=tmp_path / "home")
    assert p.returncode == 1
    assert "No config file" in p.stdout


def test_config_show_masks_secrets(tmp_path: Path):
    home = tmp_path / "home"
    _write_cfg(
        home,
        '[llm.default]\nprovider = "anthropic"\nmodel = "m"\n'
        'api_key = "sk-ant-abc123xyz789def456"\n',
    )
    p = _run("config", "show", home=home)
    assert p.returncode == 0
    assert "sk-a...f456" in p.stdout
    assert "abc123xyz789" not in p.stdout


def test_config_show_reveal(tmp_path: Path):
    home = tmp_path / "home"
    _write_cfg(
        home,
        '[llm.default]\nprovider = "anthropic"\nmodel = "m"\n'
        'api_key = "sk-ant-abc123xyz789def456"\n',
    )
    p = _run("config", "show", "--reveal", home=home)
    assert p.returncode == 0
    assert "sk-ant-abc123xyz789def456" in p.stdout
    assert "REVEAL MODE" in p.stdout


# ── check ───────────────────────────────────────────────────────────────


def test_config_check_missing(tmp_path: Path):
    p = _run("config", "check", home=tmp_path / "home")
    assert p.returncode == 1
    assert "C002" in p.stdout


def test_config_check_ok(tmp_path: Path):
    home = tmp_path / "home"
    _write_cfg(
        home,
        '[llm.default]\nprovider = "ollama"\nmodel = "qwen2.5:14b"\n'
        'base_url = "http://localhost:11434"\n',
    )
    p = _run("config", "check", home=home)
    assert p.returncode == 0
    assert "Config OK" in p.stdout


def test_config_check_bad_provider(tmp_path: Path):
    home = tmp_path / "home"
    _write_cfg(home, '[llm.default]\nprovider = "wrong"\nmodel = "x"\n')
    p = _run("config", "check", home=home)
    assert p.returncode == 1
    assert "C003" in p.stdout


def test_config_check_env_fallback_no_error(tmp_path: Path):
    home = tmp_path / "home"
    _write_cfg(
        home,
        '[llm.default]\nprovider = "anthropic"\nmodel = "m"\napi_key = ""\n',
    )
    p = _run(
        "config", "check", home=home,
        env_extra={"ANTHROPIC_API_KEY": "sk-from-env"},
    )
    assert p.returncode == 0
    # Cw01 should NOT fire when env var is present
    assert "Cw01" not in p.stdout


# ── init ────────────────────────────────────────────────────────────────


def test_config_init_refuses_non_tty(tmp_path: Path):
    # subprocess.run without stdin will attach an empty pipe → non-tty
    p = _run("config", "init", home=tmp_path / "home")
    assert p.returncode == 1
    assert "requires a terminal" in p.stderr
