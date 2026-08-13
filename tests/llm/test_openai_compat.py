"""Unit tests for OpenAI-compatible providers: OpenAI / DeepSeek / Custom.

All three share `_OpenAICompatProvider`, so protocol-level tests live here
and only per-class variance (defaults, describe, key handling) is duplicated.
"""

from __future__ import annotations

import json

import pytest

from tavern.llm import LLMAuthError, LLMError, LLMResponseError
from tavern.llm.openai_compat import (
    CustomProvider,
    DeepSeekProvider,
    OpenAIProvider,
)
from tavern.llmconfig.schema import LLMRoleConfig


# ── OpenAI ───────────────────────────────────────────────────────────────


def _openai_cfg(**over) -> LLMRoleConfig:
    return LLMRoleConfig(
        provider="openai",
        model=over.get("model", "gpt-4o"),
        api_key=over.get("api_key", "sk-test"),
        base_url=over.get("base_url", ""),
    )


def test_openai_missing_key_raises(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(LLMAuthError):
        OpenAIProvider(LLMRoleConfig(provider="openai", model="gpt-4o", api_key=""))


def test_openai_env_key_fallback(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env-openai")
    p = OpenAIProvider(LLMRoleConfig(provider="openai", model="gpt-4o", api_key=""))
    assert p._api_key == "sk-env-openai"


def test_openai_build_request_shape():
    p = OpenAIProvider(_openai_cfg())
    url, body, headers = p._build_request("hello", system="be brief", max_tokens=128)
    assert url == "https://api.openai.com/v1/chat/completions"
    assert headers["Authorization"] == "Bearer sk-test"
    assert headers["content-type"] == "application/json"
    b = json.loads(body)
    assert b["model"] == "gpt-4o"
    assert b["max_tokens"] == 128
    assert b["messages"] == [
        {"role": "system", "content": "be brief"},
        {"role": "user", "content": "hello"},
    ]


def test_openai_omits_system_when_empty():
    p = OpenAIProvider(_openai_cfg())
    _, body, _ = p._build_request("hi", system="", max_tokens=10)
    b = json.loads(body)
    roles = [m["role"] for m in b["messages"]]
    assert "system" not in roles


def test_openai_custom_base_url():
    p = OpenAIProvider(_openai_cfg(base_url="https://gateway.internal/v1/"))
    # trailing slash tolerated
    assert p._endpoint() == "https://gateway.internal/v1/chat/completions"


def test_openai_complete_via_fake_transport():
    def fake(url, body, headers):
        assert headers["Authorization"] == "Bearer sk-test"
        return {"choices": [{"message": {"role": "assistant", "content": "hi there"}}]}

    p = OpenAIProvider(_openai_cfg(), transport=fake)
    assert p.complete("hi", system="") == "hi there"


def test_openai_bad_response_shapes():
    def missing_choices(url, body, headers):
        return {"error": "nope"}

    p = OpenAIProvider(_openai_cfg(), transport=missing_choices)
    with pytest.raises(LLMResponseError):
        p.complete("hi")

    def missing_content(url, body, headers):
        return {"choices": [{"message": {"role": "assistant"}}]}

    p = OpenAIProvider(_openai_cfg(), transport=missing_content)
    with pytest.raises(LLMResponseError):
        p.complete("hi")


def test_openai_reasoning_only_response_hints_at_budget():
    # Reasoning models (DeepSeek R1/V4, o1) may spend the whole max_tokens
    # budget on chain-of-thought, returning content="" with a populated
    # reasoning_content. Error must point at that, not dump the trace.
    reasoning = "长长的推理内容" * 500

    def reasoning_only(url, body, headers):
        return {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "reasoning_content": reasoning,
                    },
                    "finish_reason": "length",
                }
            ]
        }

    p = OpenAIProvider(_openai_cfg(), transport=reasoning_only)
    with pytest.raises(LLMResponseError) as info:
        p.complete("hi")
    err = str(info.value)
    assert "max_tokens" in err
    assert reasoning not in err


def test_openai_describe_contains_model():
    p = OpenAIProvider(_openai_cfg(model="gpt-4o-mini"))
    assert p.describe() == "OpenAI gpt-4o-mini"


# ── DeepSeek ─────────────────────────────────────────────────────────────


def test_deepseek_defaults():
    p = DeepSeekProvider(
        LLMRoleConfig(provider="deepseek", model="deepseek-chat", api_key="sk-ds")
    )
    assert p._endpoint() == "https://api.deepseek.com/v1/chat/completions"
    assert "DeepSeek" in p.describe()


def test_deepseek_env_key(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-env-ds")
    p = DeepSeekProvider(
        LLMRoleConfig(provider="deepseek", model="deepseek-chat", api_key="")
    )
    assert p._api_key == "sk-env-ds"


def test_deepseek_completes_ok():
    def fake(url, body, headers):
        assert url == "https://api.deepseek.com/v1/chat/completions"
        return {"choices": [{"message": {"content": "hi ds"}}]}

    p = DeepSeekProvider(
        LLMRoleConfig(provider="deepseek", model="deepseek-chat", api_key="k"),
        transport=fake,
    )
    assert p.complete("hi") == "hi ds"


# ── Custom ───────────────────────────────────────────────────────────────


def test_custom_requires_base_url():
    with pytest.raises(LLMError, match="base_url"):
        CustomProvider(
            LLMRoleConfig(provider="custom", model="m", api_key="k", base_url="")
        )


def test_custom_requires_model():
    with pytest.raises(LLMError, match="model"):
        CustomProvider(
            LLMRoleConfig(
                provider="custom", model="", api_key="k",
                base_url="https://my.host/v1",
            )
        )


def test_custom_requires_api_key(monkeypatch):
    # ensure no env leak affects test
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(LLMAuthError):
        CustomProvider(
            LLMRoleConfig(
                provider="custom", model="m", api_key="",
                base_url="https://my.host/v1",
            )
        )


def test_custom_describe_shows_host():
    p = CustomProvider(
        LLMRoleConfig(
            provider="custom", model="my-model", api_key="k",
            base_url="https://my.host/v1",
        )
    )
    assert "my.host" in p.describe()
    assert "my-model" in p.describe()


def test_custom_endpoint():
    p = CustomProvider(
        LLMRoleConfig(
            provider="custom", model="m", api_key="k",
            base_url="https://my.host/v1",
        )
    )
    assert p._endpoint() == "https://my.host/v1/chat/completions"


def test_custom_ignores_env_key(monkeypatch):
    # Custom must NOT fall back to OPENAI_API_KEY (that's someone else's key).
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-someone-else")
    with pytest.raises(LLMAuthError):
        CustomProvider(
            LLMRoleConfig(
                provider="custom", model="m", api_key="",
                base_url="https://my.host/v1",
            )
        )


# ── messages-list input (multi-turn context) ─────────────────────────────


def test_openai_build_request_accepts_messages_list():
    p = OpenAIProvider(_openai_cfg())
    messages = [
        {"role": "user", "content": "u1"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "u2"},
    ]
    _, body_bytes, _ = p._build_request(messages, system="sys", max_tokens=64)
    body = json.loads(body_bytes)
    # OpenAI-compat: system as first message, then the list appended.
    assert body["messages"][0] == {"role": "system", "content": "sys"}
    assert body["messages"][1:] == messages


def test_openai_build_request_messages_list_no_system():
    p = OpenAIProvider(_openai_cfg())
    messages = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "ok"},
        {"role": "user", "content": "now what"},
    ]
    _, body_bytes, _ = p._build_request(messages, system="", max_tokens=64)
    body = json.loads(body_bytes)
    # No system → messages passes through unchanged.
    assert body["messages"] == messages
