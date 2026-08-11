"""Ollama provider — talks to a local `ollama serve` instance.

Uses `/api/chat` (Ollama-native) rather than the OpenAI-compatible layer,
because the native endpoint is officially supported and less likely to lag
behind Ollama features.

No API key is required; base_url defaults to `http://localhost:11434`.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Iterator

from tavern.llm._http import urllib_transport
from tavern.llm.base import (
    LLMResponseError,
    Message,
    PromptInput,
    default_stream,
)
from tavern.llmconfig.schema import LLMRoleConfig


Transport = Callable[[str, bytes, dict[str, str]], dict[str, Any]]


def _to_user_messages(prompt: PromptInput) -> list[Message]:
    if isinstance(prompt, str):
        return [{"role": "user", "content": prompt}]
    return list(prompt)


class OllamaProvider:
    DEFAULT_BASE_URL = "http://localhost:11434"
    DEFAULT_MODEL = "qwen2.5:14b"

    def __init__(
        self,
        cfg: LLMRoleConfig | None = None,
        *,
        transport: Transport | None = None,
    ):
        self.cfg = cfg or LLMRoleConfig(provider="ollama")
        self._transport = transport
        self._base_url = (self.cfg.base_url or self.DEFAULT_BASE_URL).strip()
        self._model = self.cfg.model or self.DEFAULT_MODEL

    # ── request builder ────────────────────────────────────────────

    def _endpoint(self) -> str:
        return self._base_url.rstrip("/") + "/api/chat"

    def _build_request(
        self,
        prompt: PromptInput,
        *,
        system: str,
        max_tokens: int,
    ) -> tuple[str, bytes, dict[str, str]]:
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.extend(_to_user_messages(prompt))

        body: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "stream": False,
            "options": {"num_predict": max_tokens},
        }
        headers = {"content-type": "application/json"}
        return self._endpoint(), json.dumps(body).encode("utf-8"), headers

    # ── protocol methods ────────────────────────────────────────────

    def complete(
        self,
        prompt: PromptInput,
        *,
        system: str = "",
        max_tokens: int = 1024,
    ) -> str:
        url, body, headers = self._build_request(
            prompt, system=system, max_tokens=max_tokens
        )
        transport = self._transport or urllib_transport
        data = transport(url, body, headers)
        return _extract_text(data)

    def stream(self, prompt: PromptInput, **opts) -> Iterator[str]:
        return default_stream(self, prompt, **opts)

    def describe(self) -> str:
        return f"Ollama {self._model} (local)"


# ── helpers ──────────────────────────────────────────────────────────────


def _extract_text(data: dict[str, Any]) -> str:
    """Pull assistant text out of an Ollama /api/chat response."""
    msg = data.get("message")
    if not isinstance(msg, dict):
        raise LLMResponseError(f"response missing message: {data}")
    content = msg.get("content")
    if not isinstance(content, str) or not content:
        raise LLMResponseError(f"response missing content: {msg}")
    return content
