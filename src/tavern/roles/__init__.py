"""LLM role wrappers.

Each role is a plain function that composes a specialised prompt around a
provider call. Roles have no shared state — the orchestrator wires them.
"""

from tavern.roles.suggester import (
    Suggestion,
    static_suggestions,
    suggest,
    suggestion_to_raw,
)

__all__ = [
    "Suggestion",
    "suggest",
    "static_suggestions",
    "suggestion_to_raw",
]
