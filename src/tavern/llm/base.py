"""LLM provider abstraction.

We define the shape a provider must satisfy as a `typing.Protocol` rather
than an `abc.ABC` — this keeps duck-typed test fakes viable while still
allowing `isinstance()` checks via `runtime_checkable`.

New providers only need to implement `complete()` and `describe()`. The
default `stream()` fallback wraps `complete()` as a single-chunk iterator,
which is enough to get a new provider wired up before optimising for
streaming.
"""

from __future__ import annotations

from typing import Iterator, Protocol, runtime_checkable

# A single chat message. `role` is "user" or "assistant"; system prompts stay
# a separate top-level kwarg because Anthropic keeps them outside `messages`.
Message = dict[str, str]
PromptInput = str | list[Message]


class LLMError(Exception):
    """Base class for all provider-level failures.

    CLI translates these into user-facing messages with exit code 1.
    """


class LLMAuthError(LLMError):
    """The provider rejected our credentials (401/403)."""


class LLMNetworkError(LLMError):
    """Network transport failed — timeout, DNS, refused, etc."""


class LLMResponseError(LLMError):
    """The provider responded, but not in a shape we could parse."""


@runtime_checkable
class LLMProvider(Protocol):
    """The minimum contract every provider must satisfy."""

    def complete(
        self,
        prompt: PromptInput,
        *,
        system: str = "",
        max_tokens: int = 1024,
    ) -> str:
        """Return a full text completion.

        `prompt` may be:
          * a plain string — treated as a single user message; or
          * a list of `{"role": "user"|"assistant", "content": str}` dicts,
            in chronological order. The list must end with a `user` message.

        The `system` kwarg stays separate from `messages` — Anthropic requires
        this, and it lets OpenAI-compatible providers prepend it verbatim.
        """
        ...

    def stream(
        self,
        prompt: PromptInput,
        *,
        system: str = "",
        max_tokens: int = 1024,
    ) -> Iterator[str]:
        """Yield chunks of a completion as they arrive.

        Providers may implement this natively (SSE) or fall back to a
        single-chunk yield of `complete()` — see `_default_stream` below.
        """
        ...

    def describe(self) -> str:
        """One-line label like `Anthropic claude-sonnet-5` — shown to the user."""
        ...


def default_stream(provider: LLMProvider, prompt: PromptInput, **opts) -> Iterator[str]:
    """Reusable single-chunk fallback for providers without native streaming."""
    yield provider.complete(prompt, **opts)
