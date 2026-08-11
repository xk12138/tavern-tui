"""Unit tests for OllamaProvider."""

from __future__ import annotations

import json

import pytest

from tavern.llm import LLMResponseError
from tavern.llm.ollama import OllamaProvider
from tavern.llmconfig.schema import LLMRoleConfig


def test_no_api_key_needed():
    # Should not raise even with empty api_key
    p = OllamaProvider(LLMRoleConfig(provider="ollama", model="qwen2.5:14b"))
    assert p._model == "qwen2.5:14b"


def test_default_base_url_and_model():
    # Empty cfg → defaults
    p = OllamaProvider()
    assert p._base_url == "http://localhost:11434"
    assert p._model == OllamaProvider.DEFAULT_MODEL


def test_build_request_url_and_body():
    p = OllamaProvider(
        LLMRoleConfig(provider="ollama", model="llama3", base_url="http://elsewhere:11434")
    )
    url, body, headers = p._build_request(
        "player says hi", system="be a GM", max_tokens=200,
    )
    assert url == "http://elsewhere:11434/api/chat"
    assert headers == {"content-type": "application/json"}
    b = json.loads(body)
    assert b["model"] == "llama3"
    assert b["stream"] is False
    assert b["options"]["num_predict"] == 200
    assert b["messages"] == [
        {"role": "system", "content": "be a GM"},
        {"role": "user", "content": "player says hi"},
    ]


def test_build_request_omits_system_when_empty():
    p = OllamaProvider()
    _, body, _ = p._build_request("hi", system="", max_tokens=10)
    b = json.loads(body)
    roles = [m["role"] for m in b["messages"]]
    assert "system" not in roles


def test_complete_extracts_message_content():
    def fake(url, body, headers):
        return {"model": "qwen", "message": {"role": "assistant", "content": "hi local"}}

    p = OllamaProvider(
        LLMRoleConfig(provider="ollama", model="qwen"), transport=fake,
    )
    assert p.complete("hi") == "hi local"


def test_complete_bad_response_missing_message():
    def fake(url, body, headers):
        return {"model": "qwen", "done": True}

    p = OllamaProvider(
        LLMRoleConfig(provider="ollama", model="qwen"), transport=fake,
    )
    with pytest.raises(LLMResponseError):
        p.complete("hi")


def test_complete_bad_response_missing_content():
    def fake(url, body, headers):
        return {"message": {"role": "assistant"}}

    p = OllamaProvider(
        LLMRoleConfig(provider="ollama", model="qwen"), transport=fake,
    )
    with pytest.raises(LLMResponseError):
        p.complete("hi")


def test_describe_marks_local():
    p = OllamaProvider(LLMRoleConfig(provider="ollama", model="qwen2.5:14b"))
    d = p.describe()
    assert "Ollama" in d
    assert "qwen2.5:14b" in d
    assert "local" in d


def test_base_url_trailing_slash_ok():
    p = OllamaProvider(
        LLMRoleConfig(
            provider="ollama", model="m", base_url="http://localhost:11434/"
        )
    )
    assert p._endpoint() == "http://localhost:11434/api/chat"


# ── messages-list input (multi-turn context) ─────────────────────────────


def test_ollama_build_request_accepts_messages_list():
    from tavern.llm.ollama import OllamaProvider
    from tavern.llmconfig.schema import LLMRoleConfig
    import json as _json

    p = OllamaProvider(LLMRoleConfig(provider="ollama", model="qwen"))
    messages = [
        {"role": "user", "content": "u1"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "u2"},
    ]
    _, body_bytes, _ = p._build_request(messages, system="be brief", max_tokens=64)
    body = _json.loads(body_bytes)
    assert body["messages"][0] == {"role": "system", "content": "be brief"}
    assert body["messages"][1:] == messages
