"""Shared HTTP transport for HTTP-based providers.

Every provider that talks to a remote HTTP API translates status codes and
network faults into the same LLMError subclasses, so factor the logic here
rather than copy-paste between anthropic.py / openai_compat.py / ollama.py.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from tavern.llm.base import (
    LLMAuthError,
    LLMError,
    LLMNetworkError,
    LLMResponseError,
)


def urllib_transport(
    url: str, body: bytes, headers: dict[str, str]
) -> dict[str, Any]:
    """POST `body` to `url` with `headers`; return the parsed JSON response.

    Translates:
      * HTTP 401/403 → LLMAuthError
      * other HTTP  → LLMError (`HTTP N: <detail>`)
      * URLError    → LLMNetworkError
      * bad JSON    → LLMResponseError
    """
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace") if exc.fp else str(exc)
        if exc.code in (401, 403):
            raise LLMAuthError(f"HTTP {exc.code}: {detail}") from exc
        raise LLMError(f"HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise LLMNetworkError(str(exc)) from exc

    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LLMResponseError(f"provider returned invalid JSON: {exc}") from exc
