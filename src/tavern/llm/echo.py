"""Offline demo provider.

EchoProvider does not touch the network. It's the default for smoke tests,
CI, and anyone who wants to see `tavern play` walk end-to-end before
committing an API key. The response is intentionally not-quite-GM — the
`[echo]` prefix keeps users from mistaking it for a real narrator.
"""

from __future__ import annotations

from typing import Iterator

from tavern.llm.base import PromptInput, default_stream
from tavern.llmconfig.schema import LLMRoleConfig


class EchoProvider:
    def __init__(self, cfg: LLMRoleConfig | None = None):
        self.cfg = cfg or LLMRoleConfig(provider="echo")

    def complete(
        self,
        prompt: PromptInput,
        *,
        system: str = "",
        max_tokens: int = 1024,
    ) -> str:
        # Reduce a messages list to the last user content — echoing a
        # transcript should reflect the newest player utterance, not the
        # oldest bit of assistant text.
        if isinstance(prompt, list):
            text = prompt[-1].get("content", "") if prompt else ""
        else:
            text = prompt or ""
        last = text.strip().splitlines()
        tail = last[-1] if last else ""
        if not tail:
            return "[echo] The world is still. Nothing happens."
        return f'[echo] The world hears you: "{tail}". Something stirs.'

    def stream(self, prompt: PromptInput, **opts) -> Iterator[str]:
        return default_stream(self, prompt, **opts)

    def describe(self) -> str:
        return "Echo (offline demo — does not call any LLM)"
