"""Anthropic Messages API provider.

Uses `urllib.request` so the package stays dependency-free. Streaming, tool
use, and prompt caching are intentionally out of scope for v0.4.0 — this
is the smallest working slice of `POST /v1/messages`.

Testability: `_build_request()` is pure (no I/O), and `complete()` takes a
`transport` callable in its constructor so tests can stub the HTTP layer
without touching urllib globals.
"""

from __future__ import annotations

import json
import os
from typing import Any, Callable, Iterator

from tavern.llm._http import urllib_transport
from tavern.llm.base import (
    LLMAuthError,
    LLMResponseError,
    Message,
    PromptInput,
    default_stream,
)
from tavern.llmconfig.schema import LLMRoleConfig


# (url, body_bytes, headers) → response dict
Transport = Callable[[str, bytes, dict[str, str]], dict[str, Any]]


def _to_messages(prompt: PromptInput) -> list[Message]:
    """Normalise str-or-list input into an Anthropic-shaped messages list.

    Anthropic already speaks the {role: user|assistant, content: str} shape,
    so a list passes through verbatim; a string becomes a single user turn.
    """
    if isinstance(prompt, str):
        return [{"role": "user", "content": prompt}]
    return list(prompt)


class AnthropicProvider:
    API_URL = "https://api.anthropic.com/v1/messages"
    API_VERSION = "2023-06-01"
    DEFAULT_MODEL = "claude-sonnet-5"

    def __init__(
        self,
        cfg: LLMRoleConfig | None = None,
        *,
        transport: Transport | None = None,
    ):
        self.cfg = cfg or LLMRoleConfig(provider="anthropic")
        self._transport = transport
        key = self.cfg.api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        if not key:
            raise LLMAuthError(
                "AnthropicProvider requires an api_key in config or "
                "$ANTHROPIC_API_KEY in the environment"
            )
        self._api_key = key
        self._model = self.cfg.model or self.DEFAULT_MODEL

    # ── testable pure builder ────────────────────────────────────────

    def _build_request(
        self,
        prompt: PromptInput,
        *,
        system: str,
        max_tokens: int,
    ) -> tuple[str, bytes, dict[str, str]]:
        body: dict[str, Any] = {
            "model": self._model,
            "max_tokens": max_tokens,
            "messages": _to_messages(prompt),
        }
        if system:
            body["system"] = system

        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": self.API_VERSION,
            "content-type": "application/json",
        }
        return self.API_URL, json.dumps(body).encode("utf-8"), headers

    # ── protocol methods ─────────────────────────────────────────────

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
        if self._transport is not None:
            data = self._transport(url, body, headers)
        else:
            data = urllib_transport(url, body, headers)

        return _extract_text(data)

    def stream(self, prompt: PromptInput, **opts) -> Iterator[str]:
        return default_stream(self, prompt, **opts)

    def describe(self) -> str:
        return f"Anthropic {self._model}"


# ── helpers ──────────────────────────────────────────────────────────────


def _extract_text(data: dict[str, Any]) -> str:
    """Pull the assistant text out of an Anthropic Messages API response."""
    content = data.get("content")
    if not isinstance(content, list) or not content:
        raise LLMResponseError(f"response missing content: {data}")
    parts: list[str] = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            text = block.get("text")
            if isinstance(text, str):
                parts.append(text)
    if not parts:
        raise LLMResponseError(f"response had no text blocks: {data}")
    return "".join(parts)
