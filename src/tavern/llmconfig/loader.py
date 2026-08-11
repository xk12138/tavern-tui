"""Load config.toml with env-var fallback for api keys.

Two entry points:
  * `load_config()`    → merged `Config` (env vars resolved). What the app uses.
  * `load_config_raw()` → raw dict, unmodified. What `check` uses.

Design note:  When a role's api_key is empty in the file, we look at the
provider's env_key (e.g. ANTHROPIC_API_KEY) and, if set, pull it into the
LLMRoleConfig at runtime with `api_key_from_env=True`. We never write the
resolved value back to disk — that would leak the secret into a file the
user thought was empty.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

from tavern.config import tavern_home
from tavern.llmconfig.schema import (
    PROVIDERS,
    Config,
    LLMRoleConfig,
    coerce_role,
    coerce_ui,
)


class ConfigError(Exception):
    """Raised for config-level failures other than "file doesn't exist"."""


def config_path() -> Path:
    """Return `<tavern_home>/config.toml`. Does not create the file."""
    return tavern_home() / "config.toml"


def load_config_raw() -> dict:
    """Read config.toml verbatim. Returns {} if the file doesn't exist."""
    p = config_path()
    if not p.is_file():
        return {}
    try:
        with p.open("rb") as fh:
            return tomllib.load(fh)
    except tomllib.TOMLDecodeError as exc:
        line = getattr(exc, "lineno", None)
        loc = f"{p}:{line}" if line else str(p)
        raise ConfigError(f"invalid TOML in {loc}: {exc}") from exc


def load_config() -> Config:
    """Read config.toml and resolve env-var fallbacks.

    Never raises for a missing file — returns an empty Config so callers
    can differentiate "first run" (empty) from "syntax error" (raises).
    """
    raw = load_config_raw()

    llm_raw = raw.get("llm", {}) if isinstance(raw, dict) else {}
    llm: dict[str, LLMRoleConfig] = {}
    if isinstance(llm_raw, dict):
        for role, section in llm_raw.items():
            llm[role] = coerce_role(section)

    for role_cfg in llm.values():
        _resolve_api_key_from_env(role_cfg)

    ui = coerce_ui(raw.get("ui")) if isinstance(raw, dict) else coerce_ui(None)

    return Config(llm=llm, ui=ui)


def _resolve_api_key_from_env(cfg: LLMRoleConfig) -> None:
    if cfg.api_key:
        return
    provider = cfg.provider
    meta = PROVIDERS.get(provider)
    if not meta or not meta.env_key:
        return
    env_val = os.environ.get(meta.env_key)
    if env_val:
        cfg.api_key = env_val
        cfg.api_key_from_env = True
