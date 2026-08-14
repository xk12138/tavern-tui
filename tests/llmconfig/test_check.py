"""Checker tests: one positive + one negative per relevant rule."""

from __future__ import annotations

import pytest

from tavern.llmconfig import check_config, config_path


def _write(cfg_path, body: str) -> None:
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(body, encoding="utf-8")


def test_C001_bad_toml(tavern_home):
    _write(config_path(), "[[[not toml\n")
    diags = check_config()
    codes = {d.code for d in diags}
    assert "C001" in codes


def test_C002_missing_file(tavern_home):
    diags = check_config()
    codes = {d.code for d in diags}
    assert "C002" in codes


def test_C002_missing_default_section(tavern_home, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    _write(
        config_path(),
        '[llm.extractor]\nprovider = "openai"\nmodel = "x"\napi_key = "k"\n',
    )
    diags = check_config()
    codes = {d.code for d in diags}
    assert "C002" in codes


def test_C003_bad_provider(tavern_home, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _write(
        config_path(),
        '[llm.default]\nprovider = "chatgtp"\nmodel = "x"\napi_key = "k"\n',
    )
    diags = check_config()
    codes = {d.code for d in diags}
    assert "C003" in codes


def test_C005_custom_requires_base_url(tavern_home, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    _write(
        config_path(),
        '[llm.default]\nprovider = "custom"\nmodel = "x"\napi_key = "k"\n',
    )
    diags = check_config()
    codes = {d.code for d in diags}
    assert "C005" in codes


def test_Cw01_key_missing_and_no_env(tavern_home, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _write(
        config_path(),
        '[llm.default]\nprovider = "anthropic"\nmodel = "x"\napi_key = ""\n',
    )
    diags = check_config()
    codes = {d.code for d in diags}
    assert "Cw01" in codes
    assert not any(d.level == "error" for d in diags)


def test_Ci01_key_from_env(tavern_home, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-from-env")
    _write(
        config_path(),
        '[llm.default]\nprovider = "anthropic"\nmodel = "x"\napi_key = ""\n',
    )
    diags = check_config()
    codes = {d.code for d in diags}
    assert "Ci01" in codes
    assert "Cw01" not in codes


def test_Cw03_unknown_role(tavern_home, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _write(
        config_path(),
        '[llm.default]\nprovider = "anthropic"\nmodel = "x"\napi_key = "k"\n\n'
        '[llm.mystery]\nprovider = "anthropic"\nmodel = "x"\napi_key = "k"\n',
    )
    diags = check_config()
    codes = {d.code for d in diags}
    assert "Cw03" in codes


def test_Cw02_bad_ui_speed(tavern_home, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _write(
        config_path(),
        '[llm.default]\nprovider = "anthropic"\nmodel = "x"\napi_key = "k"\n\n'
        "[ui]\ntypewriter_speed_ms = 99999\n",
    )
    diags = check_config()
    codes = {d.code for d in diags}
    assert "Cw02" in codes


def test_Cw02_bad_ui_suggestions(tavern_home):
    _write(
        config_path(),
        '[llm.default]\nprovider = "ollama"\nmodel = "qwen2.5:14b"\n'
        'base_url = "http://localhost:11434"\n\n'
        "[ui]\nsuggestions = \"yes\"\n",
    )
    diags = check_config()
    codes = {d.code for d in diags}
    assert "Cw02" in codes


def test_ui_suggestions_ok(tavern_home):
    _write(
        config_path(),
        '[llm.default]\nprovider = "ollama"\nmodel = "qwen2.5:14b"\n'
        'base_url = "http://localhost:11434"\n\n'
        "[ui]\nsuggestions = false\n",
    )
    diags = check_config()
    assert not any(d.code == "Cw02" for d in diags)


def test_all_good(tavern_home):
    _write(
        config_path(),
        '[llm.default]\nprovider = "ollama"\nmodel = "qwen2.5:14b"\n'
        'base_url = "http://localhost:11434"\n',
    )
    diags = check_config()
    assert not any(d.level == "error" for d in diags)
