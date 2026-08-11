"""Writer tests: interactive wizard + TOML serialization roundtrip."""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from tavern.llmconfig import (
    Config,
    InitError,
    LLMRoleConfig,
    UIConfig,
    config_path,
    init_interactive,
    load_config_raw,
    write_config,
)


# ── TTY guard ────────────────────────────────────────────────────────────


class _FakeStream(io.StringIO):
    def __init__(self, text: str = "", *, tty: bool = True):
        super().__init__(text)
        self._tty = tty

    def isatty(self) -> bool:
        return self._tty


def test_init_refuses_non_tty(tavern_home):
    with pytest.raises(InitError, match="requires a terminal"):
        init_interactive(
            stream_in=_FakeStream("", tty=False),
            stream_out=_FakeStream(),
        )


def test_init_refuses_when_exists(tavern_home):
    p = config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text('[llm.default]\nprovider = "anthropic"\n', encoding="utf-8")

    with pytest.raises(InitError, match="already exists"):
        init_interactive(
            stream_in=_FakeStream("", tty=True),
            stream_out=_FakeStream(),
        )


# ── wizard flow ──────────────────────────────────────────────────────────


def test_init_wizard_anthropic(tavern_home):
    # provider choice 1 (anthropic), model default, key filled
    inp = _FakeStream("1\n\nsk-ant-abc123def456\n", tty=True)
    out = _FakeStream()
    path = init_interactive(stream_in=inp, stream_out=out)

    assert path.is_file()
    raw = load_config_raw()
    assert raw["llm"]["default"]["provider"] == "anthropic"
    assert raw["llm"]["default"]["model"] == "claude-sonnet-5"
    assert raw["llm"]["default"]["api_key"] == "sk-ant-abc123def456"


def test_init_wizard_ollama_no_key(tavern_home):
    # Choice 4 is ollama; model default; base_url default; no key prompt
    inp = _FakeStream("4\n\n\n", tty=True)
    out = _FakeStream()
    path = init_interactive(stream_in=inp, stream_out=out)

    raw = load_config_raw()
    default = raw["llm"]["default"]
    assert default["provider"] == "ollama"
    # base_url written for ollama
    assert default["base_url"] == "http://localhost:11434"
    # api_key is written but empty
    assert default["api_key"] == ""


def test_init_wizard_custom_requires_base_url(tavern_home):
    # Choice 5 = custom. Model + base_url + key all needed.
    inp = _FakeStream("5\ngpt-4o-mini\nhttps://my.host/v1\nsk-abc123\n", tty=True)
    out = _FakeStream()
    init_interactive(stream_in=inp, stream_out=out)

    raw = load_config_raw()
    default = raw["llm"]["default"]
    assert default["provider"] == "custom"
    assert default["base_url"] == "https://my.host/v1"


def test_init_wizard_custom_rejects_empty_base_url(tavern_home):
    inp = _FakeStream("5\ngpt-4o-mini\n\n", tty=True)
    out = _FakeStream()
    with pytest.raises(InitError, match="base_url is required"):
        init_interactive(stream_in=inp, stream_out=out)


def test_init_provider_hint(tavern_home):
    # --provider anthropic — user still supplies model + key
    inp = _FakeStream("\nsk-ant-xyz\n", tty=True)
    out = _FakeStream()
    init_interactive(
        stream_in=inp,
        stream_out=out,
        provider_hint="anthropic",
    )
    raw = load_config_raw()
    assert raw["llm"]["default"]["provider"] == "anthropic"
    assert raw["llm"]["default"]["api_key"] == "sk-ant-xyz"


def test_init_provider_hint_rejects_unknown(tavern_home):
    with pytest.raises(InitError, match="unknown provider"):
        init_interactive(
            stream_in=_FakeStream("\n", tty=True),
            stream_out=_FakeStream(),
            provider_hint="bogus",
        )


def test_init_force_overwrites(tavern_home):
    p = config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("stale=true\n", encoding="utf-8")

    inp = _FakeStream("1\n\nsk-new\n", tty=True)
    out = _FakeStream()
    init_interactive(stream_in=inp, stream_out=out, force=True)

    raw = load_config_raw()
    assert raw["llm"]["default"]["provider"] == "anthropic"


# ── programmatic writer ──────────────────────────────────────────────────


def test_write_config_roundtrip(tavern_home):
    cfg = Config(
        llm={
            "default": LLMRoleConfig(
                provider="anthropic",
                model="claude-sonnet-5",
                api_key='sk-with-"quotes"-and\\backslash',
            )
        },
        ui=UIConfig(typewriter_speed_ms=30, color_scheme="dark"),
    )
    write_config(cfg)
    raw = load_config_raw()
    assert raw["llm"]["default"]["api_key"] == 'sk-with-"quotes"-and\\backslash'
    assert raw["ui"]["typewriter_speed_ms"] == 30
    assert raw["ui"]["color_scheme"] == "dark"


def test_write_config_atomic_no_tmp_leftover(tavern_home):
    cfg = Config(
        llm={"default": LLMRoleConfig(provider="anthropic", model="x", api_key="k")}
    )
    write_config(cfg)
    parent = config_path().parent
    stale = [p for p in parent.iterdir() if p.name.endswith(".tmp")]
    assert stale == []
