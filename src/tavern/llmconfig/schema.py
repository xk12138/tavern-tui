"""LLM configuration: schema, provider registry, and helpers.

Kept as a package (`llmconfig/`) rather than a module so we can grow it —
loader, writer, and check live in separate files even though each is small.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ProviderMeta:
    """Static metadata about a supported LLM provider."""

    default_model: str
    env_key: str | None
    needs_key: bool
    default_base_url: str = ""
    display_name: str = ""
    hint: str = ""


PROVIDERS: dict[str, ProviderMeta] = {
    "anthropic": ProviderMeta(
        default_model="claude-sonnet-5",
        env_key="ANTHROPIC_API_KEY",
        needs_key=True,
        display_name="Anthropic",
        hint="Claude models (recommended for Narrator)",
    ),
    "openai": ProviderMeta(
        default_model="gpt-4o",
        env_key="OPENAI_API_KEY",
        needs_key=True,
        display_name="OpenAI",
        hint="GPT models",
    ),
    "deepseek": ProviderMeta(
        default_model="deepseek-chat",
        env_key="DEEPSEEK_API_KEY",
        needs_key=True,
        display_name="DeepSeek",
        hint="Cheap and fast — good for Extractor",
    ),
    "ollama": ProviderMeta(
        default_model="qwen2.5:14b",
        env_key=None,
        needs_key=False,
        default_base_url="http://localhost:11434",
        display_name="Ollama",
        hint="Local models (no API key needed)",
    ),
    "custom": ProviderMeta(
        default_model="",
        env_key=None,
        needs_key=True,
        display_name="Custom",
        hint="Any OpenAI-compatible endpoint",
    ),
    "echo": ProviderMeta(
        default_model="",
        env_key=None,
        needs_key=False,
        display_name="Echo",
        hint="Offline demo — echoes your input without calling any LLM",
    ),
}


# Roles we track separately in [llm.<role>] sections.
LLM_ROLES = ("default", "extractor", "director", "memory_keeper", "export", "suggest")


@dataclass
class LLMRoleConfig:
    """One [llm.<role>] section."""

    provider: str = ""
    model: str = ""
    api_key: str = ""
    base_url: str = ""
    # Runtime-only: set when api_key was resolved from an env var, not the file.
    api_key_from_env: bool = False


@dataclass
class UIConfig:
    """The [ui] section."""

    typewriter_speed_ms: int = 20
    color_scheme: str = "default"
    # Show the suggested-player-line list after each GM reply. Off disables
    # the per-turn LLM suggestion call entirely.
    suggestions: bool = True


@dataclass
class Config:
    """Full parsed config.

    `llm` maps role name → LLMRoleConfig. `default` is required at runtime,
    but at load time we tolerate its absence so `init` can bootstrap.
    """

    llm: dict[str, LLMRoleConfig] = field(default_factory=dict)
    ui: UIConfig = field(default_factory=UIConfig)


# ── helpers ──────────────────────────────────────────────────────────────


_SECRET_PATTERNS = ("key", "secret", "token", "password", "apikey")


def is_secret_field(name: str) -> bool:
    """Return True if a field name is likely a secret and should be masked."""
    lower = name.lower()
    return any(p in lower for p in _SECRET_PATTERNS)


def mask_secret(v: str) -> str:
    """Return a masked form of a secret string.

      ""          -> ""
      "short"     -> "***"
      "sk-abcd..1234"  -> "sk-a...1234"
    """
    if not v:
        return ""
    if len(v) < 8:
        return "***"
    return f"{v[:4]}...{v[-4:]}"


def coerce_role(raw: Any) -> LLMRoleConfig:
    """Best-effort build an LLMRoleConfig from a TOML dict."""
    if not isinstance(raw, dict):
        return LLMRoleConfig()
    return LLMRoleConfig(
        provider=str(raw.get("provider", "")),
        model=str(raw.get("model", "")),
        api_key=str(raw.get("api_key", "")),
        base_url=str(raw.get("base_url", "")),
    )


def coerce_ui(raw: Any) -> UIConfig:
    if not isinstance(raw, dict):
        return UIConfig()
    ui = UIConfig()
    if isinstance(raw.get("typewriter_speed_ms"), int):
        ui.typewriter_speed_ms = raw["typewriter_speed_ms"]
    if isinstance(raw.get("color_scheme"), str):
        ui.color_scheme = raw["color_scheme"]
    if isinstance(raw.get("suggestions"), bool):
        ui.suggestions = raw["suggestions"]
    return ui
