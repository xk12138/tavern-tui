"""End-to-end tests for `tavern export novel` and REPL `/export novel`."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
SRC = Path(__file__).resolve().parent.parent.parent / "src"


def _run(*args: str, home: Path, novels: Path, stdin: str | None = None):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC)
    env["NO_COLOR"] = "1"
    env["TAVERN_CONFIG_HOME"] = str(home)
    env["TAVERN_NOVELS_HOME"] = str(novels)
    env.pop("XDG_CONFIG_HOME", None)
    return subprocess.run(
        [sys.executable, "-m", "tavern", *args],
        input=stdin,
        capture_output=True,
        text=True,
        env=env,
    )


def _bootstrap(home: Path, novels: Path, world_src: Path = FIXTURES / "full-ok") -> None:
    home.mkdir(parents=True, exist_ok=True)
    (home / "config.toml").write_text(
        '[llm.default]\nprovider = "echo"\nmodel = ""\napi_key = ""\n',
        encoding="utf-8",
    )
    _run("install", str(world_src), home=home, novels=novels)


# ── top-level `tavern export novel` ─────────────────────────────────────


def test_export_novel_full_flow(tmp_path: Path):
    home = tmp_path / "home"
    novels = tmp_path / "novels"
    _bootstrap(home, novels)
    _run("play", "full-ok", home=home, novels=novels, stdin="hi\n/quit\n")

    p = _run("export", "novel", "default-full-ok", home=home, novels=novels)
    assert p.returncode == 0, p.stdout + p.stderr
    assert "Novel exported to" in p.stdout
    md_files = list(novels.glob("*.md"))
    assert len(md_files) == 1
    content = md_files[0].read_text(encoding="utf-8")
    assert "---" in content   # front matter
    assert "full-ok" in content


def test_export_novel_missing_save(tmp_path: Path):
    home = tmp_path / "home"
    novels = tmp_path / "novels"
    _bootstrap(home, novels)
    p = _run("export", "novel", "nonexistent", home=home, novels=novels)
    assert p.returncode == 1
    assert "not found" in p.stderr


def test_export_novel_empty_save(tmp_path: Path):
    home = tmp_path / "home"
    novels = tmp_path / "novels"
    _bootstrap(home, novels)
    # Create save via play but immediately quit (save has 1 system opening only)
    _run("play", "full-ok", home=home, novels=novels, stdin="/quit\n")
    # This save has a system opening but no player/gm pair — still exportable
    # since pairs list is empty but opening exists → no ExportError.
    p = _run("export", "novel", "default-full-ok", home=home, novels=novels)
    # Should succeed: opening-only saves are allowed.
    assert p.returncode == 0


def test_export_novel_custom_output(tmp_path: Path):
    home = tmp_path / "home"
    novels = tmp_path / "novels"
    _bootstrap(home, novels)
    _run("play", "full-ok", home=home, novels=novels, stdin="hi\n/quit\n")

    out = tmp_path / "story" / "my-tale.md"
    p = _run(
        "export", "novel", "default-full-ok",
        "--output", str(out),
        home=home, novels=novels,
    )
    assert p.returncode == 0
    assert out.is_file()


def test_export_novel_target_exists(tmp_path: Path):
    home = tmp_path / "home"
    novels = tmp_path / "novels"
    _bootstrap(home, novels)
    _run("play", "full-ok", home=home, novels=novels, stdin="hi\n/quit\n")

    out = tmp_path / "clash.md"
    out.write_text("stale")

    p = _run(
        "export", "novel", "default-full-ok",
        "--output", str(out),
        home=home, novels=novels,
    )
    assert p.returncode == 1
    assert "already exists" in p.stderr

    # --force overrides
    p = _run(
        "export", "novel", "default-full-ok",
        "--output", str(out),
        "--force",
        home=home, novels=novels,
    )
    assert p.returncode == 0
    assert out.read_text(encoding="utf-8") != "stale"


def test_export_novel_provider_role_fallback(tmp_path: Path):
    """When [llm.export] is missing, export uses [llm.default]."""
    home = tmp_path / "home"
    novels = tmp_path / "novels"
    _bootstrap(home, novels)   # only sets [llm.default]
    _run("play", "full-ok", home=home, novels=novels, stdin="hi\n/quit\n")

    p = _run("export", "novel", "default-full-ok", home=home, novels=novels)
    assert p.returncode == 0


def test_export_novel_explicit_provider_role(tmp_path: Path):
    home = tmp_path / "home"
    novels = tmp_path / "novels"
    _bootstrap(home, novels)
    # Add a specific export role to config (still Echo, so no network)
    (home / "config.toml").write_text(
        '[llm.default]\nprovider = "echo"\n'
        '[llm.export]\nprovider = "echo"\n',
        encoding="utf-8",
    )
    _run("play", "full-ok", home=home, novels=novels, stdin="hi\n/quit\n")

    p = _run(
        "export", "novel", "default-full-ok",
        "--provider", "export",
        home=home, novels=novels,
    )
    assert p.returncode == 0


def test_export_help_lists_novel(tmp_path: Path):
    p = _run("export", "--help", home=tmp_path, novels=tmp_path)
    assert p.returncode == 0
    assert "novel" in p.stdout


# ── REPL /export novel ──────────────────────────────────────────────────


def test_repl_export_novel_default_path(tmp_path: Path):
    home = tmp_path / "home"
    novels = tmp_path / "novels"
    _bootstrap(home, novels)

    p = _run(
        "play", "full-ok",
        home=home, novels=novels,
        stdin="hello there\n/export novel\n/quit\n",
    )
    assert p.returncode == 0
    assert "Novel exported to" in p.stdout
    assert list(novels.glob("*.md"))


def test_repl_export_novel_custom_path(tmp_path: Path):
    home = tmp_path / "home"
    novels = tmp_path / "novels"
    _bootstrap(home, novels)
    out = tmp_path / "repl-story.md"

    p = _run(
        "play", "full-ok",
        home=home, novels=novels,
        stdin=f"hello\n/export novel {out}\n/quit\n",
    )
    assert p.returncode == 0
    assert out.is_file()


def test_repl_export_novel_survives_after_error(tmp_path: Path):
    """A bad /export command should print an error but not exit the REPL."""
    home = tmp_path / "home"
    novels = tmp_path / "novels"
    _bootstrap(home, novels)

    p = _run(
        "play", "full-ok",
        home=home, novels=novels,
        stdin="/export bogus\n/quit\n",
    )
    assert p.returncode == 0
    assert "usage:" in p.stdout.lower() or "[error]" in p.stdout
    assert "Goodbye" in p.stdout


def test_repl_export_help_mentions_export(tmp_path: Path):
    home = tmp_path / "home"
    novels = tmp_path / "novels"
    _bootstrap(home, novels)
    p = _run(
        "play", "full-ok",
        home=home, novels=novels,
        stdin="/help\n/quit\n",
    )
    assert "/export novel" in p.stdout
