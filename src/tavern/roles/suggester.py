"""Suggester — the scene-suggestion role.

Every GM turn the play loop asks this role for up to `max_n` lines the
PLAYER character could say, think, or do next, written in the player's own
first-person voice. The play loop renders them as a selectable list (arrow
keys, Claude Code style); the player may pick one or simply type their own
thing — suggestions are hints, never rails.

Design choices:
  * The LLM output is already in the input-prefix grammar (`S:` / `T:` /
    `A:`), so picking a suggestion needs zero translation: the chosen line
    is converted to its prefix-equivalent raw text and re-enters the normal
    `parse_input` pipeline. The save stores the player-voice line itself,
    so novels and rewinds read like the player really typed it.
  * `suggest()` NEVER raises. A provider failure (or a response that
    doesn't parse) silently falls back to the worldpack's static
    suggestions — the GM reply the player already saw is never endangered.
  * Static worldpack suggestions (`[[world.initial_tavern.suggestions]]`)
    take priority and fill the slots first; dynamic ones top up the rest.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from tavern.llm.base import LLMProvider
from tavern.save.store import Save
from tavern.worldpack.schema import WorldPack

SuggestionKind = Literal["say", "think", "action"]

_LINE_RE = re.compile(r"^\s*([STA])\s*:\s*(.+?)\s*$")
_MAX_LINE_CHARS = 200


@dataclass
class Suggestion:
    """One suggested player line, in the player's own first-person voice."""

    kind: SuggestionKind
    text: str


# ── LLM call budget ───────────────────────────────────────────────────────
#
# The suggestion output itself is tiny (~3 lines), but reasoning models
# (DeepSeek R1/V4, o1, extended-thinking Claude, …) burn their max_tokens
# budget on chain-of-thought BEFORE writing the answer. A small cap means
# the answer never gets written and suggestions silently vanish — the exact
# bug fixed here.
#
# 32768 gives reasoning models plenty of CoT headroom (DeepSeek reasoner
# allows up to 64k). Some endpoints reject large max_tokens outright
# (gpt-4o caps at 16k, Anthropic Opus at 32k, DeepSeek chat at 8k), so on
# rejection we retry once with a conservative cap — a failed giant value
# must not take the whole feature down with it.
_SUGGEST_MAX_TOKENS = 32768
_SUGGEST_RETRY_TOKENS = 4096


# ── prompt ────────────────────────────────────────────────────────────────


_SYSTEM_PROMPT_TEMPLATE = """\
You are the suggestion writer for an interactive story set in the world "{world_name}".

The player is mid-scene and needs ideas for what to do next. Write up to {max_n} lines
the PLAYER character could say, think, or do — written exactly as the player would
type them, in the player's own first-person voice.

Rules:
- Always write from the player's first-person perspective. Never narrate the scene,
  describe other characters, or speak for anyone else.
- Only reference people, objects, places, or events already visible in the scene.
  Never invent new facts, new NPCs, or new plot.
- Vary the kinds. Prefer speech (S:) and actions (A:). Use thoughts (T:) sparingly
  — at most one.
- Match the player's recent style: terse if they are terse, elaborate if they are
  elaborate.
- Do not repeat what the player just did.

Scene so far:
{scene}

Player's recent lines (style reference only):
{player_lines}

Output exactly {max_n} lines, one per suggestion, no preamble, no numbering:
S: "the spoken line"
T: *the inner thought*
A: the action"""


# ── public API ────────────────────────────────────────────────────────────


def suggest(
    provider: LLMProvider,
    pack: WorldPack,
    save: Save,
    *,
    static: list[Suggestion] | None = None,
    max_n: int = 3,
) -> list[Suggestion]:
    """Generate suggestions for the current scene.

    Static suggestions are placed first; dynamic LLM ones top up to `max_n`.
    Never raises: any provider failure or unparseable reply falls back to
    whatever static suggestions were given.
    """
    static = static or []
    dynamic = _generate(provider, pack, save, max_n=max_n)
    return _merge(static, dynamic, max_n=max_n)


def static_suggestions(pack: WorldPack) -> list[Suggestion]:
    """Extract worldpack-authored suggestions from `[world.initial_tavern]`.

    Shape: `[[world.initial_tavern.suggestions]]` with `kind` and `text`.
    Invalid entries are silently skipped (the validator surfaces them as W010).
    """
    raw = pack.world.initial_tavern.get("suggestions", [])
    if not isinstance(raw, list):
        return []
    out: list[Suggestion] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        kind = item.get("kind")
        text = item.get("text")
        if kind not in ("say", "think", "action"):
            continue
        if not isinstance(text, str) or not text.strip():
            continue
        out.append(Suggestion(kind=kind, text=text.strip()))
    return out


def suggestion_to_raw(s: Suggestion) -> str:
    """The prefix-equivalent raw input for a suggestion.

    `say` becomes `"..."`, `think` becomes `*...*`, `action` stays bare —
    exactly what the player would have typed, so `parse_input` round-trips
    it and the save stores a genuine player-voice line.
    """
    if s.kind == "say":
        return f'"{s.text}"'
    if s.kind == "think":
        return f"*{s.text}*"
    return s.text


# ── internals ─────────────────────────────────────────────────────────────


def _generate(
    provider: LLMProvider, pack: WorldPack, save: Save, *, max_n: int
) -> list[Suggestion]:
    """One lightweight LLM call (plus a degrade-and-retry); [] on failure.

    Tries `_SUGGEST_MAX_TOKENS` (32768) for reasoning-model CoT headroom;
    if the provider rejects that value, retries once with
    `_SUGGEST_RETRY_TOKENS` (4096) before giving up. Never raises.
    """
    try:
        reply = _complete_once(provider, pack, save, max_n=max_n, max_tokens=_SUGGEST_MAX_TOKENS)
    except Exception:
        # Endpoint caps max_tokens (e.g. gpt-4o 16k, DeepSeek chat 8k,
        # Anthropic Opus 32k) — retry with a conservative cap.
        try:
            reply = _complete_once(provider, pack, save, max_n=max_n, max_tokens=_SUGGEST_RETRY_TOKENS)
        except Exception:
            return []
    return _parse_suggestions(reply)


def _complete_once(
    provider: LLMProvider, pack: WorldPack, save: Save, *, max_n: int, max_tokens: int
) -> str:
    system = _SYSTEM_PROMPT_TEMPLATE.format(
        world_name=pack.world.name,
        max_n=max_n,
        scene=_scene_context(save, pack),
        player_lines=_player_style(save),
    )
    user = "Write the suggestions now."
    return provider.complete(user, system=system, max_tokens=max_tokens)


def _scene_context(save: Save, pack: WorldPack, n_gm: int = 2) -> str:
    """The scene the player is looking at, for the suggester.

    Normally the last GM reply or two. Before any turn has been played the
    save has no GM rows, so we seed from the world's `opening_hook` — this
    is what lets the very first prompt of a fresh game carry a real LLM
    recommendation instead of nothing.
    """
    turns = save.recent_turns(8)
    gm = [t.text.strip() for t in turns if t.role == "gm"][-n_gm:]
    if gm:
        return "\n".join(f"- {t}" for t in gm)
    hook = str(pack.world.initial_tavern.get("opening_hook", "")).strip()
    if hook:
        return "(opening scene)\n" + hook
    return "(the scene has just begun)"


def _player_style(save: Save, n_player: int = 3) -> str:
    turns = save.recent_turns(8)
    lines = [t.text.strip() for t in turns if t.role == "player"][-n_player:]
    if not lines:
        return "(no prior player input)"
    return "\n".join(f"- {t}" for t in lines)


def _parse_suggestions(reply: str) -> list[Suggestion]:
    """Parse `S: / T: / A:` lines out of a provider reply.

    Unparseable or over-long lines are dropped rather than guessed at — a
    Narrator-ish paragraph leaking into the output must not become a
    suggestion.
    """
    out: list[Suggestion] = []
    for line in reply.splitlines():
        m = _LINE_RE.match(line)
        if not m:
            continue
        kind = {"S": "say", "T": "think", "A": "action"}[m.group(1)]
        text = _clean_text(m.group(2))
        if not text or len(text) > _MAX_LINE_CHARS:
            continue
        out.append(Suggestion(kind=kind, text=text))  # type: ignore[arg-type]
    return out


def _clean_text(raw: str) -> str:
    """Strip wrapping quotes/stars the model may have added around the line."""
    text = raw.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ('"', "*"):
        text = text[1:-1].strip()
    return text


def _merge(
    static: list[Suggestion],
    dynamic: list[Suggestion],
    *,
    max_n: int,
) -> list[Suggestion]:
    """Static first, then dynamic; dedupe on (kind, normalised text); cap."""
    seen: set[tuple[str, str]] = set()
    out: list[Suggestion] = []
    for s in [*static, *dynamic]:
        key = (s.kind, " ".join(s.text.split()))
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
        if len(out) >= max_n:
            break
    return out
