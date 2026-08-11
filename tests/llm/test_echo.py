"""Contract & basic tests for LLMProvider protocol + EchoProvider."""

from __future__ import annotations

from tavern.llm import LLMProvider
from tavern.llm.echo import EchoProvider
from tavern.llmconfig.schema import LLMRoleConfig


def test_echo_conforms_to_protocol():
    provider = EchoProvider(LLMRoleConfig(provider="echo"))
    # Protocol is @runtime_checkable — this actually exercises the shape.
    assert isinstance(provider, LLMProvider)


def test_echo_returns_something_for_empty_input():
    provider = EchoProvider()
    out = provider.complete("")
    assert isinstance(out, str) and out.strip() != ""


def test_echo_echoes_last_line():
    provider = EchoProvider()
    out = provider.complete("hello world")
    assert "hello world" in out
    assert out.startswith("[echo]")


def test_echo_stream_yields_full_completion():
    provider = EchoProvider()
    chunks = list(provider.stream("hi"))
    joined = "".join(chunks)
    assert joined == provider.complete("hi")


def test_echo_describe_mentions_offline():
    provider = EchoProvider()
    assert "Echo" in provider.describe()
    assert "offline" in provider.describe().lower()


def test_echo_reads_last_line_when_multiline():
    provider = EchoProvider()
    out = provider.complete("earlier context\nfinal action")
    assert "final action" in out
    assert "earlier context" not in out


# ── messages-list input (multi-turn context) ─────────────────────────────


def test_echo_accepts_messages_list_echoes_last_user():
    from tavern.llm.echo import EchoProvider

    p = EchoProvider()
    out = p.complete([
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "second"},
        {"role": "user", "content": "third and last"},
    ])
    # Echo picks the last user content's last line.
    assert "third and last" in out
    assert out.startswith("[echo]")


def test_echo_empty_messages_list():
    from tavern.llm.echo import EchoProvider
    p = EchoProvider()
    out = p.complete([])
    assert "still" in out or "Nothing happens" in out
