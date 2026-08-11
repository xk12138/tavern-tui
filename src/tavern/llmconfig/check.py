"""Config checker.

Produces a list of Diagnostics for TOML syntax, required sections, provider
validity, key presence (or env-var fallback), and misc. quality warnings.

Uses the same `Diagnostic` type as the worldpack validator so the CLI's
render path can be shared.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

from tavern.llmconfig.loader import config_path
from tavern.llmconfig.schema import LLM_ROLES, PROVIDERS
from tavern.worldpack.diagnostics import Diagnostic


def check_config() -> list[Diagnostic]:
    """Run all checks against the on-disk config.toml.

    Returns Diagnostics in stable order. Empty list = perfectly fine.
    A file that doesn't exist yields C002 (no [llm.default]) because from
    the user's perspective an empty file and a missing file are the same
    "not configured yet" state.
    """
    p: Path = config_path()

    if not p.is_file():
        return [
            Diagnostic(
                level="error",
                code="C002",
                message="no config file",
                location=str(p),
                hint="run `tavern config init` to create one",
            )
        ]

    try:
        with p.open("rb") as fh:
            raw = tomllib.load(fh)
    except tomllib.TOMLDecodeError as exc:
        line = getattr(exc, "lineno", None)
        loc = f"{p}:{line}" if line else str(p)
        return [
            Diagnostic(
                level="error",
                code="C001",
                message=f"invalid TOML: {exc}",
                location=loc,
                hint="check syntax near the line above",
            )
        ]

    diags: list[Diagnostic] = []

    llm = raw.get("llm")
    if not isinstance(llm, dict) or "default" not in llm:
        diags.append(
            Diagnostic(
                level="error",
                code="C002",
                message="[llm.default] section is required",
                location=str(p),
                hint="run `tavern config init`, or add `[llm.default]` with provider/model/api_key",
            )
        )
        return diags

    # ── per-role checks ────────────────────────────────────────────────
    for role, section in llm.items():
        if not isinstance(section, dict):
            diags.append(
                Diagnostic(
                    level="error",
                    code="C002",
                    message=f"[llm.{role}] is not a table",
                    location=str(p),
                )
            )
            continue
        diags.extend(_check_role(role, section, p))

    # ── unknown top-level sections (typo protection) ───────────────────
    known_top = {"llm", "ui"}
    for k in raw:
        if k not in known_top:
            diags.append(
                Diagnostic(
                    level="warning",
                    code="Cw03",
                    message=f"unknown top-level section [{k}]",
                    location=str(p),
                    hint=f"expected one of: {', '.join(sorted(known_top))}",
                )
            )

    # ── unknown role sections ──────────────────────────────────────────
    for role in llm:
        if role not in LLM_ROLES:
            diags.append(
                Diagnostic(
                    level="warning",
                    code="Cw03",
                    message=f"unknown LLM role [llm.{role}]",
                    location=str(p),
                    hint=f"expected one of: {', '.join(LLM_ROLES)}",
                )
            )

    # ── ui checks ──────────────────────────────────────────────────────
    ui = raw.get("ui")
    if isinstance(ui, dict):
        speed = ui.get("typewriter_speed_ms")
        if speed is not None and (not isinstance(speed, int) or speed < 0 or speed > 1000):
            diags.append(
                Diagnostic(
                    level="warning",
                    code="Cw02",
                    message=f"[ui].typewriter_speed_ms={speed!r} is out of range",
                    location=str(p),
                    hint="expected an integer in [0, 1000]",
                )
            )

    return diags


def _check_role(role: str, section: dict, path: Path) -> list[Diagnostic]:
    out: list[Diagnostic] = []
    provider = section.get("provider", "")

    if not provider:
        out.append(
            Diagnostic(
                level="error",
                code="C003",
                message=f"[llm.{role}] missing provider",
                location=str(path),
                hint=f"one of: {', '.join(sorted(PROVIDERS))}",
            )
        )
        return out

    if provider not in PROVIDERS:
        out.append(
            Diagnostic(
                level="error",
                code="C003",
                message=f"[llm.{role}].provider = '{provider}' is not a known provider",
                location=str(path),
                hint=f"valid providers: {', '.join(sorted(PROVIDERS))}",
            )
        )
        return out

    meta = PROVIDERS[provider]

    # model
    if not section.get("model") and meta.default_model:
        # not a fatal — many providers accept no model at runtime with default
        out.append(
            Diagnostic(
                level="warning",
                code="C004",
                message=f"[llm.{role}] has no model set",
                location=str(path),
                hint=f"consider `model = \"{meta.default_model}\"`",
            )
        )

    # custom requires base_url
    if provider == "custom" and not section.get("base_url"):
        out.append(
            Diagnostic(
                level="error",
                code="C005",
                message=f"[llm.{role}] uses custom provider but has no base_url",
                location=str(path),
                hint="add `base_url = \"https://...\"`",
            )
        )

    # api_key: config or env
    if meta.needs_key:
        key_in_config = bool(section.get("api_key"))
        key_in_env = bool(meta.env_key and os.environ.get(meta.env_key))
        if not key_in_config and not key_in_env:
            out.append(
                Diagnostic(
                    level="warning",
                    code="Cw01",
                    message=f"[llm.{role}].api_key is empty and ${meta.env_key} is not set",
                    location=str(path),
                    hint=(
                        f"set api_key in config, or export ${meta.env_key} before running"
                    ),
                )
            )
        elif not key_in_config and key_in_env:
            out.append(
                Diagnostic(
                    level="info",
                    code="Ci01",
                    message=f"[llm.{role}].api_key resolved from ${meta.env_key}",
                    location=str(path),
                )
            )

    return out
