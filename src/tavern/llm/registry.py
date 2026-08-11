"""Provider registry + factory.

Providers are addressed by name in config.toml; this module maps that name
to a concrete class. Classes are looked up by dotted string (`module:Class`)
so importing the registry does NOT import every provider — a slow `httpx`
in one provider wouldn't punish startup for someone using only Echo.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

from tavern.llm.base import LLMError, LLMProvider
from tavern.llmconfig import load_config
from tavern.llmconfig.schema import LLMRoleConfig

if TYPE_CHECKING:
    from tavern.llmconfig.schema import Config


PROVIDER_CLASSES: dict[str, str] = {
    "echo": "tavern.llm.echo:EchoProvider",
    "anthropic": "tavern.llm.anthropic:AnthropicProvider",
    "openai": "tavern.llm.openai_compat:OpenAIProvider",
    "deepseek": "tavern.llm.openai_compat:DeepSeekProvider",
    "custom": "tavern.llm.openai_compat:CustomProvider",
    "ollama": "tavern.llm.ollama:OllamaProvider",
}


def load_provider(
    role: str = "default",
    *,
    cfg: "Config | None" = None,
) -> LLMProvider:
    """Instantiate the provider for `role` (falling back to "default").

    Raises LLMError with a user-actionable message if configuration is
    missing or the provider name is unrecognised.
    """
    if cfg is None:
        cfg = load_config()

    role_cfg = cfg.llm.get(role) or cfg.llm.get("default")
    if role_cfg is None:
        raise LLMError(
            "no [llm.default] configured. Run `tavern config init`."
        )

    provider_name = role_cfg.provider
    if not provider_name:
        raise LLMError(
            f"[llm.{role}].provider is empty. Run `tavern config init`."
        )
    if provider_name not in PROVIDER_CLASSES:
        valid = ", ".join(sorted(PROVIDER_CLASSES))
        raise LLMError(
            f"unknown provider '{provider_name}'. Valid providers: {valid}"
        )

    return _instantiate(PROVIDER_CLASSES[provider_name], role_cfg)


def _instantiate(dotted: str, cfg: LLMRoleConfig) -> LLMProvider:
    module_path, _, class_name = dotted.partition(":")
    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)
    return cls(cfg)
