"""Rewrite a save's turn log into a prose novel via an LLM.

Design notes:
  * The engine is pure orchestration — it takes an already-open Save and an
    already-instantiated provider, so the CLI layer is free to pick the
    "export" role vs the "default" role without this module knowing.
  * We chunk the transcript by character count. LLM tokenisation varies
    wildly per provider, so a char threshold is a coarse-but-safe stand-in.
  * Chunks flow through the LLM in order, each seeded with the tail of the
    previous chunk's output for continuity.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from pathlib import Path

from tavern.export.paths import default_output_path
from tavern.llm.base import LLMError, LLMProvider
from tavern.save import Save, Turn
from tavern.worldpack.schema import WorldPack


# ── errors ───────────────────────────────────────────────────────────────


class ExportError(Exception):
    """Business-level export failure (empty save, target conflict, etc.)."""


# ── result ───────────────────────────────────────────────────────────────


@dataclass
class ExportResult:
    output_path: Path
    turn_count: int
    chunk_count: int


# ── public entry ────────────────────────────────────────────────────────


DEFAULT_THRESHOLD_CHARS = 5000
_TAIL_CHARS = 300


def export_novel(
    save: Save,
    world_pack: WorldPack | None,
    provider: LLMProvider,
    *,
    output: Path | None = None,
    force: bool = False,
    threshold_chars: int = DEFAULT_THRESHOLD_CHARS,
) -> ExportResult:
    """Produce a markdown novel from `save` and write it to disk.

    Raises ExportError on empty saves and on target-exists (unless `force`).
    Passes LLMError through if the provider fails.
    """
    turns = save.turns()
    opening, pairs = _pair_turns(turns)

    if not pairs and not opening:
        raise ExportError(
            f"save '{save.name}' has no turns to export"
        )

    if output is None:
        output = default_output_path(save.name)
    output = Path(output).expanduser()

    if output.exists() and not force:
        raise ExportError(
            f"output '{output}' already exists; pass force=True to overwrite"
        )

    output.parent.mkdir(parents=True, exist_ok=True)

    chunks = _build_chunks(pairs, threshold_chars=threshold_chars)
    novel_body = _generate_novel(
        chunks=chunks,
        opening=opening,
        world_pack=world_pack,
        provider=provider,
    )

    intro_text = _extract_intro(world_pack, opening)
    rendered = _render_output(
        result_text=novel_body,
        save=save,
        world_pack=world_pack,
        provider=provider,
        intro_text=intro_text,
    )

    output.write_text(rendered, encoding="utf-8")

    return ExportResult(
        output_path=output,
        turn_count=len(pairs),
        chunk_count=max(1, len(chunks)),
    )


# ── generation loop ─────────────────────────────────────────────────────


def _generate_novel(
    *,
    chunks: list[list[tuple[Turn, Turn]]],
    opening: str | None,
    world_pack: WorldPack | None,
    provider: LLMProvider,
) -> str:
    if not chunks:
        # opening-only save: still produce something so the file isn't empty
        return (opening or "").strip()

    world_name = world_pack.world.name if world_pack else "Unknown world"
    tone = (
        str(world_pack.world.setting.get("tone", "")).strip()
        if world_pack
        else ""
    )

    outputs: list[str] = []
    for i, chunk in enumerate(chunks):
        transcript = _format_transcript(chunk)
        is_first = i == 0
        previous_tail = _last_paragraph(outputs[-1]) if outputs else ""

        system_prompt = _build_novel_system_prompt(world_name, tone)
        user_prompt = _build_user_prompt(
            transcript=transcript,
            opening=opening if is_first else None,
            previous_tail=previous_tail,
        )

        try:
            text = provider.complete(user_prompt, system=system_prompt, max_tokens=2048)
        except LLMError:
            # Bubble up — the caller wants to surface provider failures.
            raise

        outputs.append(text.strip())

    return "\n\n".join(outputs)


# ── prompts ─────────────────────────────────────────────────────────────


def _build_novel_system_prompt(world_name: str, tone: str) -> str:
    parts = [
        "You are a novelist adapting an interactive story into prose fiction.",
        f"World: {world_name}",
    ]
    if tone:
        parts.append(f"Setting tone: {tone}")
    parts.append(
        "Rewrite the transcript as a coherent third-person past-tense narrative.\n"
        "Rules:\n"
        "- Third-person past tense.\n"
        "- Preserve every meaningful action, dialogue, and outcome.\n"
        "- Do NOT invent plot points not in the transcript.\n"
        "- Do NOT add meta-commentary or break the fourth wall.\n"
        "- Use the world's tone. If tone is empty, default to neutral prose.\n"
        "- Output only the story text — no headings, no 'Chapter', no notes."
    )
    return "\n\n".join(parts)


def _build_user_prompt(
    *,
    transcript: str,
    opening: str | None,
    previous_tail: str,
) -> str:
    sections: list[str] = []
    if previous_tail:
        sections.append(
            "This is a continuation. Here is the last paragraph you wrote:\n\n"
            f"{previous_tail}\n\n"
            "Continue seamlessly. Do NOT repeat what came before."
        )
    if opening:
        sections.append(f"Opening scene:\n\n{opening.strip()}")
    sections.append(f"Transcript:\n\n{transcript}")
    sections.append("Now write the narrative for this section.")
    return "\n\n".join(sections)


# ── transcript formatting ───────────────────────────────────────────────


def _pair_turns(turns: list[Turn]) -> tuple[str | None, list[tuple[Turn, Turn]]]:
    """Extract opening + pair up player/gm turns.

    - First `system` role turn (if any) → opening_text.
    - Later `system` turns are dropped (they're engine annotations).
    - Every `player` turn is paired with the *next* `gm` turn.
    - Orphans (unpaired player or gm) are skipped — they'd only appear if
      the save was hand-edited.
    """
    opening: str | None = None
    pairs: list[tuple[Turn, Turn]] = []
    pending_player: Turn | None = None

    for t in turns:
        if t.role == "system":
            if opening is None:
                opening = t.text
            continue
        if t.role == "player":
            pending_player = t
            continue
        if t.role == "gm":
            if pending_player is not None:
                pairs.append((pending_player, t))
                pending_player = None
            # gm with no preceding player: skip
    return opening, pairs


def _format_transcript(pairs: list[tuple[Turn, Turn]]) -> str:
    lines: list[str] = []
    for p, g in pairs:
        lines.append(f"Player: {p.text.strip()}")
        lines.append(f"GM: {g.text.strip()}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _build_chunks(
    pairs: list[tuple[Turn, Turn]],
    *,
    threshold_chars: int,
) -> list[list[tuple[Turn, Turn]]]:
    """Greedily accumulate pairs into chunks until threshold is exceeded."""
    if not pairs:
        return []
    chunks: list[list[tuple[Turn, Turn]]] = []
    current: list[tuple[Turn, Turn]] = []
    current_size = 0
    for p, g in pairs:
        size = len(p.text) + len(g.text)
        if current and (current_size + size) > threshold_chars:
            chunks.append(current)
            current = []
            current_size = 0
        current.append((p, g))
        current_size += size
    if current:
        chunks.append(current)
    return chunks


def _last_paragraph(text: str, max_chars: int = _TAIL_CHARS) -> str:
    """Return the trailing paragraph (up to max_chars) for continuity prompts."""
    if not text:
        return ""
    tail = text.rstrip()
    # find last blank line separator
    idx = tail.rfind("\n\n")
    para = tail[idx + 2 :] if idx >= 0 else tail
    if len(para) > max_chars:
        para = para[-max_chars:]
    return para


# ── output rendering ────────────────────────────────────────────────────


def _extract_intro(pack: WorldPack | None, opening: str | None) -> str | None:
    """The intro paragraph shown before the novel body.

    Prefer pack.intro (Markdown); fall back to world.description; then the
    opening_hook itself.
    """
    if pack is None:
        return opening
    if pack.intro and pack.intro.strip():
        return pack.intro.strip()
    if pack.world.description.strip():
        return pack.world.description.strip()
    return opening


def _render_output(
    *,
    result_text: str,
    save: Save,
    world_pack: WorldPack | None,
    provider: LLMProvider,
    intro_text: str | None,
) -> str:
    front = _render_frontmatter(save, world_pack, provider)
    parts = [front, "\n"]
    world_name = world_pack.world.name if world_pack else save.world_id
    parts.append(f"# {world_name}\n\n")
    if intro_text:
        parts.append(intro_text.strip())
        parts.append("\n\n---\n\n")
    parts.append(result_text.strip())
    parts.append("\n\n")
    parts.append(_render_footer(save))
    return "".join(parts)


def _render_frontmatter(
    save: Save, pack: WorldPack | None, provider: LLMProvider
) -> str:
    from tavern import __version__

    world_name = pack.world.name if pack else save.world_id
    now = (
        _dt.datetime.now(tz=_dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
    lines = [
        "---",
        f'title: "{_yaml_escape(world_name)} · {_yaml_escape(save.name)}"',
        f'world: "{_yaml_escape(save.world_id)}"',
        f'save: "{_yaml_escape(save.name)}"',
        f"turns: {save.state.turn_count}",
        f'provider: "{_yaml_escape(provider.describe())}"',
        f'generated_at: "{now}"',
        f'tavern_version: "{__version__}"',
        "---",
        "",
    ]
    return "\n".join(lines)


def _render_footer(save: Save) -> str:
    now = _dt.datetime.now(tz=_dt.timezone.utc).strftime("%Y-%m-%d")
    return (
        f"*本篇由 Tavern 于 {now} 从存档 `{save.name}` 生成。"
        f"turn 数:{save.state.turn_count}。*\n"
    )


def _yaml_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")
