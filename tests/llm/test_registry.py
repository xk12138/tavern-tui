"""Registry tests: load_provider dispatch, fallbacks, error messages."""

from __future__ import annotations

import pytest

from tavern.llm import LLMError, load_provider
from tavern.llm.echo import EchoProvider
from tavern.llm.ollama import OllamaProvider
from tavern.llm.openai_compat import (
    CustomProvider,
    DeepSeekProvider,
    OpenAIProvider,
)
from tavern.llmconfig.schema import Config, LLMRoleConfig


def _cfg(**roles: LLMRoleConfig) -> Config:
    return Config(llm=dict(roles))


def test_load_echo_provider():
    cfg = _cfg(default=LLMRoleConfig(provider="echo"))
    p = load_provider("default", cfg=cfg)
    assert isinstance(p, EchoProvider)


def test_load_missing_default_raises():
    with pytest.raises(LLMError, match="no \\[llm.default\\]"):
        load_provider("default", cfg=Config())


def test_load_unknown_provider_raises():
    cfg = _cfg(default=LLMRoleConfig(provider="gpt5"))
    with pytest.raises(LLMError, match="unknown provider"):
        load_provider("default", cfg=cfg)


def test_load_empty_provider_name_raises():
    cfg = _cfg(default=LLMRoleConfig(provider=""))
    with pytest.raises(LLMError):
        load_provider("default", cfg=cfg)


def test_load_role_fallback_to_default():
    # Ask for "extractor" but only default is set → fall back
    cfg = _cfg(default=LLMRoleConfig(provider="echo"))
    p = load_provider("extractor", cfg=cfg)
    assert isinstance(p, EchoProvider)


def test_load_role_specific_wins():
    cfg = _cfg(
        default=LLMRoleConfig(provider="echo"),
        extractor=LLMRoleConfig(provider="echo"),
    )
    p = load_provider("extractor", cfg=cfg)
    assert isinstance(p, EchoProvider)


# ── new-provider dispatch ────────────────────────────────────────────────


def test_load_openai(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    cfg = _cfg(default=LLMRoleConfig(
        provider="openai", model="gpt-4o", api_key="sk-test",
    ))
    assert isinstance(load_provider("default", cfg=cfg), OpenAIProvider)


def test_load_deepseek():
    cfg = _cfg(default=LLMRoleConfig(
        provider="deepseek", model="deepseek-chat", api_key="sk-ds",
    ))
    assert isinstance(load_provider("default", cfg=cfg), DeepSeekProvider)


def test_load_ollama_no_key():
    cfg = _cfg(default=LLMRoleConfig(
        provider="ollama", model="qwen2.5:14b",
    ))
    assert isinstance(load_provider("default", cfg=cfg), OllamaProvider)


def test_load_custom_requires_base_url():
    cfg = _cfg(default=LLMRoleConfig(
        provider="custom", model="m", api_key="k",
    ))
    with pytest.raises(LLMError, match="base_url"):
        load_provider("default", cfg=cfg)


def test_load_custom_happy_path():
    cfg = _cfg(default=LLMRoleConfig(
        provider="custom", model="m", api_key="k",
        base_url="https://my.host/v1",
    ))
    assert isinstance(load_provider("default", cfg=cfg), CustomProvider)
