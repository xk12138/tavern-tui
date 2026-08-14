"""Interactive `tavern config init` + programmatic TOML writer.

Writes atomically via <path>.tmp + os.replace so a Ctrl+C never leaves a
half-written file.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from tavern.config import ensure_dirs
from tavern.llmconfig.loader import config_path
from tavern.llmconfig.schema import PROVIDERS, Config, LLMRoleConfig, UIConfig


class InitAborted(Exception):
    """User pressed Ctrl+C / Ctrl+D during the wizard."""


class InitError(Exception):
    """Init cannot proceed (existing config, non-tty, bad input)."""


def init_interactive(
    *,
    force: bool = False,
    provider_hint: str | None = None,
    stream_in=None,
    stream_out=None,
) -> Path:
    """Run the interactive wizard. Returns the path written to.

    `stream_in` / `stream_out` are injectable for testing; default to
    stdin/stdout. When stdin is not a TTY, we refuse to run — automation
    should write config.toml directly rather than fake keystrokes.
    """
    stream_in = stream_in if stream_in is not None else sys.stdin
    stream_out = stream_out if stream_out is not None else sys.stdout

    path = config_path()

    if path.exists() and not force:
        raise InitError(
            f"config already exists at {path}; pass --force to overwrite"
        )

    if not stream_in.isatty():
        raise InitError(
            "`tavern config init` is interactive and requires a terminal; "
            "edit config.toml directly for scripted setup"
        )

    try:
        cfg = _run_wizard(stream_in, stream_out, provider_hint)
    except (KeyboardInterrupt, EOFError):
        raise InitAborted()

    ensure_dirs()
    write_config(cfg, path=path)
    return path


def _run_wizard(
    stream_in,
    stream_out,
    provider_hint: str | None,
) -> Config:
    def out(msg: str = "") -> None:
        stream_out.write(msg + "\n")
        stream_out.flush()

    def ask(prompt: str, default: str = "") -> str:
        suffix = f" [{default}]" if default else ""
        stream_out.write(f"{prompt}{suffix}: ")
        stream_out.flush()
        line = stream_in.readline()
        if line == "":
            raise EOFError()
        answer = line.rstrip("\n").strip()
        return answer or default

    out("")
    out("Welcome to Tavern. Let's set up your LLM.")
    out("")

    # ── provider ──────────────────────────────────────────────────────
    if provider_hint:
        if provider_hint not in PROVIDERS:
            raise InitError(
                f"unknown provider '{provider_hint}'; "
                f"expected one of: {', '.join(sorted(PROVIDERS))}"
            )
        provider = provider_hint
        out(f"Provider (from --provider): {provider}")
    else:
        provider_list = list(PROVIDERS.keys())
        out("Which provider?")
        for i, p in enumerate(provider_list, 1):
            meta = PROVIDERS[p]
            out(f"  {i}) {p:<10}  {meta.hint}")
        raw = ask("Choice", default="1")
        provider = _resolve_provider_choice(raw, provider_list)

    meta = PROVIDERS[provider]

    # ── model ─────────────────────────────────────────────────────────
    default_model = meta.default_model
    model = ask("Model", default=default_model)
    if not model and provider != "custom":
        raise InitError("model cannot be empty for this provider")

    # ── base_url (only for ollama / custom) ───────────────────────────
    base_url = ""
    if provider in ("ollama", "custom"):
        base_url = ask("Base URL", default=meta.default_base_url)
        if provider == "custom" and not base_url:
            raise InitError("base_url is required for custom provider")

    # ── api_key ───────────────────────────────────────────────────────
    api_key = ""
    if meta.needs_key:
        env_prompt = (
            f" (or leave blank to use ${meta.env_key})" if meta.env_key else ""
        )
        api_key = ask(f"API key{env_prompt}")

    cfg = Config(
        llm={
            "default": LLMRoleConfig(
                provider=provider,
                model=model,
                api_key=api_key,
                base_url=base_url,
            )
        },
        ui=UIConfig(),
    )
    return cfg


def _resolve_provider_choice(raw: str, provider_list: list[str]) -> str:
    """Accept either the number or the provider name."""
    if raw.isdigit():
        idx = int(raw) - 1
        if 0 <= idx < len(provider_list):
            return provider_list[idx]
        raise InitError(f"choice must be 1..{len(provider_list)}")
    if raw in PROVIDERS:
        return raw
    raise InitError(f"unknown provider '{raw}'")


# ── writer ────────────────────────────────────────────────────────────


def write_config(cfg: Config, *, path: Path | None = None) -> Path:
    """Serialize Config to TOML and write atomically."""
    if path is None:
        path = config_path()

    text = _to_toml(cfg)
    ensure_dirs()
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
    return path


def _to_toml(cfg: Config) -> str:
    """Minimal, deterministic TOML writer for our Config shape.

    Not a general-purpose emitter — we know exactly what fields exist.
    """
    lines: list[str] = []

    for role in ("default", "extractor", "director", "memory_keeper", "export", "suggest"):
        role_cfg = cfg.llm.get(role)
        if role_cfg is None:
            continue
        lines.append(f"[llm.{role}]")
        _emit_str(lines, "provider", role_cfg.provider)
        _emit_str(lines, "model", role_cfg.model)
        _emit_str(lines, "api_key", role_cfg.api_key)
        if role_cfg.base_url:
            _emit_str(lines, "base_url", role_cfg.base_url)
        lines.append("")

    lines.append("[ui]")
    lines.append(f"typewriter_speed_ms = {cfg.ui.typewriter_speed_ms}")
    _emit_str(lines, "color_scheme", cfg.ui.color_scheme)
    lines.append("")

    return "\n".join(lines).lstrip("\n")


def _emit_str(lines: list[str], key: str, value: str) -> None:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    lines.append(f'{key} = "{escaped}"')
