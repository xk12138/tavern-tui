"""memory_keeper.compress: prompt shape + echo round-trip."""

from __future__ import annotations

from tavern.llm.echo import EchoProvider
from tavern.roles.memory_keeper import compress
from tavern.save.store import Turn
from tavern.worldpack.loader import load_worldpack


def _fake_turns(n: int) -> list[Turn]:
    out: list[Turn] = []
    for i in range(1, n + 1):
        out.append(Turn(id=2 * i - 1, turn_no=i, role="player",
                        text=f"player line {i}", created_at=""))
        out.append(Turn(id=2 * i, turn_no=i, role="gm",
                        text=f"gm reply {i}", created_at=""))
    return out


def test_compress_first_pass_no_prior(FIXTURES_DIR):
    pack = load_worldpack(FIXTURES_DIR / "minimal-ok").pack
    out = compress(EchoProvider(), None, _fake_turns(5), pack)
    # Echo returns "[echo] The world hears you: \"<last-line>\". Something stirs."
    assert out.startswith("[echo]")
    # Last line of the constructed user prompt is "Write the updated summary now."
    # so echo picks that up — confirms the transcript + prior-none framing reached the provider.
    assert "Write the updated summary now" in out


def test_compress_second_pass_with_prior(FIXTURES_DIR):
    pack = load_worldpack(FIXTURES_DIR / "minimal-ok").pack
    prior = "In an earlier chapter, you met the guildmaster."
    out = compress(EchoProvider(), prior, _fake_turns(3), pack)
    assert out.startswith("[echo]")


def test_compress_captures_provider_output_verbatim_after_strip(FIXTURES_DIR):
    """Whatever the provider returns is the summary, minus surrounding whitespace."""
    pack = load_worldpack(FIXTURES_DIR / "minimal-ok").pack

    class WhitespaceProvider:
        def complete(self, prompt, *, system="", max_tokens=1024):
            return "\n\n  a tidy summary  \n"
        def stream(self, prompt, **opts):  # not used
            yield self.complete(prompt, **opts)
        def describe(self) -> str:
            return "whitespace"

    out = compress(WhitespaceProvider(), None, _fake_turns(2), pack)
    assert out == "a tidy summary"
