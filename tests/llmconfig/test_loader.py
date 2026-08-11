"""Loader tests: file-missing, env-var fallback, syntax errors."""

from __future__ import annotations

from pathlib import Path

import pytest

from tavern.llmconfig import (
    ConfigError,
    config_path,
    load_config,
    load_config_raw,
)


def test_load_missing_file_returns_empty(tavern_home):
    cfg = load_config()
    assert cfg.llm == {}


def test_load_raw_missing_file_returns_empty_dict(tavern_home):
    assert load_config_raw() == {}


def test_load_reads_llm_default(tavern_home, monkeypatch):
    # ensure ANTHROPIC_API_KEY doesn't leak in from the developer environment
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    cfg_path = config_path()
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(
        '[llm.default]\nprovider = "anthropic"\nmodel = "claude-sonnet-5"\n'
        'api_key = "sk-ant-abc123"\n',
        encoding="utf-8",
    )
    cfg = load_config()
    assert cfg.llm["default"].provider == "anthropic"
    assert cfg.llm["default"].api_key == "sk-ant-abc123"
    assert cfg.llm["default"].api_key_from_env is False


def test_env_fallback_when_key_empty(tavern_home, monkeypatch):
    cfg_path = config_path()
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(
        '[llm.default]\nprovider = "anthropic"\nmodel = "x"\napi_key = ""\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-from-env")

    cfg = load_config()
    assert cfg.llm["default"].api_key == "sk-from-env"
    assert cfg.llm["default"].api_key_from_env is True


def test_env_fallback_only_when_key_empty(tavern_home, monkeypatch):
    cfg_path = config_path()
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(
        '[llm.default]\nprovider = "anthropic"\nmodel = "x"\napi_key = "sk-in-file"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-from-env")

    cfg = load_config()
    assert cfg.llm["default"].api_key == "sk-in-file"
    assert cfg.llm["default"].api_key_from_env is False


def test_load_raw_bad_toml_raises(tavern_home):
    cfg_path = config_path()
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text("[[[not toml\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config_raw()


def test_load_ui_section(tavern_home):
    cfg_path = config_path()
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(
        '[llm.default]\nprovider = "ollama"\nmodel = "x"\n\n'
        '[ui]\ntypewriter_speed_ms = 50\ncolor_scheme = "dark"\n',
        encoding="utf-8",
    )
    cfg = load_config()
    assert cfg.ui.typewriter_speed_ms == 50
    assert cfg.ui.color_scheme == "dark"
