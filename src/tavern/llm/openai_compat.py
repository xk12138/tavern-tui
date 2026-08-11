"""OpenAI-compatible providers: OpenAI, DeepSeek, Custom.

All three speak the same `/chat/completions` protocol, so the shared base
class carries almost everything. Subclasses just override endpoint / key /
model defaults.

Ollama has its own `/api/chat` shape and lives in `ollama.py`.
"""

from __future__ import annotations

import json
import os
from typing import Any, Callable, Iterator
from urllib.parse import urlparse

from tavern.llm._http import urllib_transport
from tavern.llm.base import (
    LLMAuthError,
    LLMError,
    LLMResponseError,
    Message,
    PromptInput,
    default_stream,
)
from tavern.llmconfig.schema import LLMRoleConfig


Transport = Callable[[str, bytes, dict[str, str]], dict[str, Any]]


def _to_user_messages(prompt: PromptInput) -> list[Message]:
    """Normalise str-or-list input into a user/assistant messages list.

    A bare string becomes a single user message. A list passes through
    unchanged — the caller is responsible for role order.
    """
    if isinstance(prompt, str):
        return [{"role": "user", "content": prompt}]
    return list(prompt)


class _OpenAICompatProvider:
    """Shared base for OpenAI-flavoured Chat Completions endpoints.

    Subclasses set BASE_URL / DEFAULT_MODEL / ENV_KEY / DISPLAY_NAME /
    NEEDS_KEY as class attributes. They rarely need to override methods.
    """

    BASE_URL: str = ""
    DEFAULT_MODEL: str = ""
    ENV_KEY: str = ""
    DISPLAY_NAME: str = "OpenAI"
    NEEDS_KEY: bool = True

    def __init__(
        self,
        cfg: LLMRoleConfig | None = None,
        *,
        transport: Transport | None = None,
    ):
        self.cfg = cfg or LLMRoleConfig(provider=self.DISPLAY_NAME.lower())
        self._transport = transport

        # base_url: config wins, else class default. Must not be empty.
        base = (self.cfg.base_url or self.BASE_URL).strip()
        if not base:
            raise LLMError(
                f"{self.DISPLAY_NAME}Provider requires a base_url"
            )
        self._base_url = base

        # api key: config → env → error
        key = self.cfg.api_key
        if not key and self.ENV_KEY:
            key = os.environ.get(self.ENV_KEY, "")
        if self.NEEDS_KEY and not key:
            hint = f" or ${self.ENV_KEY} in the environment" if self.ENV_KEY else ""
            raise LLMAuthError(
                f"{self.DISPLAY_NAME}Provider requires an api_key in config{hint}"
            )
        self._api_key = key

        model = self.cfg.model or self.DEFAULT_MODEL
        if not model:
            raise LLMError(
                f"{self.DISPLAY_NAME}Provider requires a model in config"
            )
        self._model = model

    # ── endpoint & request builder ──────────────────────────────────

    def _endpoint(self) -> str:
        return self._base_url.rstrip("/") + "/chat/completions"

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
            "max_tokens": max_tokens,
            "messages": messages,
        }
        headers = {"content-type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

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
        return f"{self.DISPLAY_NAME} {self._model}"


# ── concrete providers ───────────────────────────────────────────────────


class OpenAIProvider(_OpenAICompatProvider):
    BASE_URL = "https://api.openai.com/v1"
    DEFAULT_MODEL = "gpt-4o"
    ENV_KEY = "OPENAI_API_KEY"
    DISPLAY_NAME = "OpenAI"


class DeepSeekProvider(_OpenAICompatProvider):
    BASE_URL = "https://api.deepseek.com/v1"
    DEFAULT_MODEL = "deepseek-chat"
    ENV_KEY = "DEEPSEEK_API_KEY"
    DISPLAY_NAME = "DeepSeek"


class CustomProvider(_OpenAICompatProvider):
    """Any OpenAI-compatible endpoint the user runs themselves.

    Explicit — no env-var fallback, no default model, no default base_url.
    If the user reaches for Custom they've done their own homework.
    """

    BASE_URL = ""
    DEFAULT_MODEL = ""
    ENV_KEY = ""
    DISPLAY_NAME = "Custom"
    NEEDS_KEY = True

    def describe(self) -> str:
        parsed = urlparse(self._base_url)
        host = parsed.netloc or parsed.path or self._base_url
        return f"Custom ({host}) {self._model}"


# ── helpers ──────────────────────────────────────────────────────────────


def _extract_text(data: dict[str, Any]) -> str:
    """Pull assistant text out of an OpenAI Chat Completions response."""
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise LLMResponseError(f"response missing choices: {data}")
    first = choices[0]
    if not isinstance(first, dict):
        raise LLMResponseError(f"response choice not a dict: {first}")
    msg = first.get("message")
    if not isinstance(msg, dict):
        raise LLMResponseError(f"response missing message: {first}")
    content = msg.get("content")
    if not isinstance(content, str) or not content:
        raise LLMResponseError(f"response missing content: {msg}")
    return content
