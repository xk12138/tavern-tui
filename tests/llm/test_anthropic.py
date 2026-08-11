"""Unit tests for AnthropicProvider.

These tests exercise the request-building logic and error paths via an
injected transport — no network calls are made.
"""

from __future__ import annotations

import json

import pytest

from tavern.llm import LLMAuthError, LLMError, LLMResponseError
from tavern.llm.anthropic import AnthropicProvider
from tavern.llmconfig.schema import LLMRoleConfig


def _cfg(api_key: str = "sk-test", model: str = "claude-sonnet-5") -> LLMRoleConfig:
    return LLMRoleConfig(provider="anthropic", model=model, api_key=api_key)


# ── construction ─────────────────────────────────────────────────────────


def test_missing_api_key_raises(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(LLMAuthError):
        AnthropicProvider(LLMRoleConfig(provider="anthropic", api_key=""))


def test_env_fallback_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-env")
    provider = AnthropicProvider(LLMRoleConfig(provider="anthropic", api_key=""))
    # if constructor didn't raise, key resolved
    assert provider._api_key == "sk-env"


def test_default_model_used_when_missing(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-env")
    provider = AnthropicProvider(LLMRoleConfig(provider="anthropic", api_key="", model=""))
    assert provider._model == AnthropicProvider.DEFAULT_MODEL


# ── request builder (pure) ───────────────────────────────────────────────


def test_build_request_shape():
    provider = AnthropicProvider(_cfg())
    url, body_bytes, headers = provider._build_request(
        "hello there", system="be brief", max_tokens=256,
    )
    assert url == AnthropicProvider.API_URL
    assert headers["x-api-key"] == "sk-test"
    assert headers["anthropic-version"] == AnthropicProvider.API_VERSION
    assert headers["content-type"] == "application/json"

    body = json.loads(body_bytes)
    assert body["model"] == "claude-sonnet-5"
    assert body["max_tokens"] == 256
    assert body["system"] == "be brief"
    assert body["messages"] == [{"role": "user", "content": "hello there"}]


def test_build_request_omits_empty_system():
    provider = AnthropicProvider(_cfg())
    _, body_bytes, _ = provider._build_request("hi", system="", max_tokens=10)
    body = json.loads(body_bytes)
    assert "system" not in body


# ── complete via injected transport ──────────────────────────────────────


def test_complete_extracts_text():
    captured: dict = {}

    def fake_transport(url, body, headers):
        captured["url"] = url
        captured["body"] = json.loads(body)
        return {
            "id": "msg_1",
            "content": [{"type": "text", "text": "Hi there!"}],
        }

    provider = AnthropicProvider(_cfg(), transport=fake_transport)
    reply = provider.complete("hello", system="be nice", max_tokens=100)
    assert reply == "Hi there!"
    assert captured["url"] == AnthropicProvider.API_URL
    assert captured["body"]["messages"][0]["content"] == "hello"


def test_complete_joins_multiple_text_blocks():
    def fake_transport(url, body, headers):
        return {
            "content": [
                {"type": "text", "text": "Part one. "},
                {"type": "text", "text": "Part two."},
            ]
        }

    provider = AnthropicProvider(_cfg(), transport=fake_transport)
    assert provider.complete("hi") == "Part one. Part two."


def test_complete_raises_on_missing_content():
    def fake_transport(url, body, headers):
        return {"error": "something"}

    provider = AnthropicProvider(_cfg(), transport=fake_transport)
    with pytest.raises(LLMResponseError):
        provider.complete("hi")


def test_complete_raises_on_no_text_blocks():
    def fake_transport(url, body, headers):
        return {"content": [{"type": "tool_use", "id": "x"}]}

    provider = AnthropicProvider(_cfg(), transport=fake_transport)
    with pytest.raises(LLMResponseError):
        provider.complete("hi")


# ── describe ─────────────────────────────────────────────────────────────


def test_describe_includes_model():
    provider = AnthropicProvider(_cfg(model="claude-fable-5"))
    assert "claude-fable-5" in provider.describe()
    assert "Anthropic" in provider.describe()


# ── messages-list input (multi-turn context) ─────────────────────────────


def test_build_request_accepts_messages_list():
    provider = AnthropicProvider(_cfg())
    messages = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello back"},
        {"role": "user", "content": "how are you"},
    ]
    _, body_bytes, _ = provider._build_request(messages, system="be nice", max_tokens=128)
    body = json.loads(body_bytes)
    # Anthropic takes the messages list verbatim; system stays top-level.
    assert body["messages"] == messages
    assert body["system"] == "be nice"


def test_complete_with_messages_list():
    captured: dict = {}

    def fake_transport(url, body, headers):
        captured["body"] = json.loads(body)
        return {"content": [{"type": "text", "text": "ack"}]}

    provider = AnthropicProvider(_cfg(), transport=fake_transport)
    messages = [
        {"role": "user", "content": "one"},
        {"role": "assistant", "content": "two"},
        {"role": "user", "content": "three"},
    ]
    assert provider.complete(messages, system="s") == "ack"
    assert captured["body"]["messages"] == messages
