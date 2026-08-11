"""Input-prefix parser: `"..."` `*...*` `/xxx` `:xxx` and default.

The REPL sends the raw line here; the returned `Intent` says both what the
player meant AND how the LLM should be told about it. Two properties matter:

- `intent.raw`  — the player's exact bytes; this is what gets persisted
  into the save so novel export sees what was really typed.
- `intent.llm_line` — a normalised "Player says (aloud): ..." style line,
  which is what actually reaches provider.complete().

Parsing rules are documented in USAGE.md §五. We deliberately do not try to
support nested prefixes (`*"..."*`) or escapes — the moment the outer prefix
doesn't cleanly close, we fall back to `action` and treat the whole line as
free-form.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Kind = Literal["say", "think", "action", "shortcut", "slash"]


@dataclass
class Intent:
    kind: Kind
    body: str           # cleaned body (prefixes stripped)
    raw: str            # original line, verbatim — this is what gets saved
    llm_line: str       # normalised line to send to the LLM (empty for slash)


# Well-known shortcut expansions. Unknown `:xxx` fall through as-is via
# `Player quickly does: <xxx>` so worldpacks can invent their own without
# needing this table to know about them.
SHORTCUT_MAP: dict[str, str] = {
    "look": "looks around, taking in the scene",
    "wait": "waits, watching what happens",
    "rest": "takes a moment to rest and gather thoughts",
    "inventory": "quickly checks their belongings",
    "map": "tries to recall the layout of the area",
    "recap": "pauses to reflect on what has happened so far",
}


def parse_input(raw: str) -> Intent:
    """Classify a raw REPL input line into an Intent."""
    stripped = raw.strip()

    if not stripped:
        return _build("action", "", raw)

    if stripped.startswith("/"):
        # Whole thing (with the slash) is the slash command.
        return _build("slash", stripped, raw)

    # Speech: "..."
    if len(stripped) >= 2 and stripped.startswith('"') and stripped.endswith('"'):
        body = stripped[1:-1]
        return _build("say", body, raw)

    # Thought: *...*
    if len(stripped) >= 2 and stripped.startswith("*") and stripped.endswith("*"):
        body = stripped[1:-1]
        return _build("think", body, raw)

    # Shortcut: :xxx (at least one char after the colon)
    if stripped.startswith(":") and len(stripped) > 1:
        body = stripped[1:]
        return _build("shortcut", body, raw)

    return _build("action", stripped, raw)


def _build(kind: Kind, body: str, raw: str) -> Intent:
    return Intent(kind=kind, body=body, raw=raw, llm_line=_to_llm_line(kind, body))


def _to_llm_line(kind: Kind, body: str) -> str:
    if kind == "say":
        return f'Player says (aloud): "{body}"'
    if kind == "think":
        return f'Player thinks (internal, unheard by others): "{body}"'
    if kind == "shortcut":
        expanded = SHORTCUT_MAP.get(body, body)
        return f"Player quickly does: {expanded}"
    if kind == "slash":
        return ""
    return f"Player does: {body}"


INPUT_SYNTAX_PROMPT = (
    "The player uses the following input conventions when talking to you:\n"
    '- "..."   = the character speaks aloud\n'
    "- *...*   = the character's private thoughts (do NOT let other characters hear)\n"
    "- :xxx    = a quick, common action\n"
    "- otherwise = a free-form action\n"
    "Each turn's user message will be prefixed with the intent, e.g. "
    '`Player says (aloud): "..."` or `Player thinks (internal, unheard by others): "..."`.\n'
    "Treat internal thoughts as private — no NPC should react to them."
)
