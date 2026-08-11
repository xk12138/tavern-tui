"""Turn-context assembly for the play loop.

Two responsibilities:

1. `build_system_prompt(pack, summary_text=None)` — the world-static header
   that opens every LLM call. Optionally prepends the running scene summary
   (L2 memory) so the Narrator inherits condensed history.

2. `build_turn_messages(save, pack, intent, *, raw_window)` — assembles the
   full LLM input for one turn: system prompt + last N raw player+gm pairs
   as a messages list + the current player intent as the final user message.

The raw window replays stored player rows through `parse_input(row.text)` so
the LLM sees the same `llm_line` framing it received when the turn was live
— we only persist raw text (DESIGN.md §四), not llm_line, so it must be
rebuilt on read. Cheap: parsing is regex-driven with no I/O.

System-role rows (opening hook at turn_no=0) are intentionally skipped in
the messages list. Once a scene_summary exists, the hook's content has been
absorbed into it; before then, the system prompt itself already carries the
world setup, so replaying the hook as a user turn is worse than useless.
"""

from __future__ import annotations

from collections import OrderedDict

from tavern.llm.base import Message
from tavern.repl.parser import INPUT_SYNTAX_PROMPT, Intent, parse_input
from tavern.save.store import Save, Turn
from tavern.worldpack.schema import WorldPack


DEFAULT_RAW_WINDOW = 10  # last N logical turns kept as raw messages


def build_system_prompt(pack: WorldPack, summary_text: str | None = None) -> str:
    """Return the world-static Narrator system prompt.

    If `summary_text` is provided, it's appended as a "Previously in this
    story:" block so the Narrator has condensed long-term context.
    """
    tone = str(pack.world.setting.get("tone", "")).strip()
    rules = str(pack.world.rules.get("summary", "")).strip()
    parts = [
        f'You are the Narrator (GM) of a story set in the world "{pack.world.name}".',
    ]
    if tone:
        parts.append(f"World tone: {tone}")
    if rules:
        parts.append(f"World rules:\n{rules}")
    parts.append(INPUT_SYNTAX_PROMPT)
    parts.append(
        "Respond in second person, present tense. Keep replies under 3 short paragraphs. "
        "Do not break character."
    )
    if summary_text:
        parts.append("Previously in this story:\n" + summary_text)
    return "\n\n".join(parts)


def build_turn_messages(
    save: Save,
    pack: WorldPack,
    intent: Intent,
    *,
    raw_window: int = DEFAULT_RAW_WINDOW,
) -> tuple[str, list[Message]]:
    """Assemble (system_prompt, messages) for one turn's provider.complete call.

    Historical player rows are re-parsed via `parse_input` to reconstruct
    their `llm_line` framing. GM rows are used verbatim as `assistant`
    content. The current `intent.llm_line` is appended as the trailing
    user message.
    """
    summary = save.summary()
    system = build_system_prompt(
        pack, summary_text=summary.summary_text if summary else None
    )

    cutoff = summary.covered_up_to_turn if summary else 0
    raw_turns = save.turns_after(cutoff)

    # Group by turn_no in insertion order. Skip any system rows (only the
    # opening hook at turn_no=0 uses that role, and it would be filtered by
    # cutoff=0 → turn_no > 0 anyway; belt-and-braces).
    grouped: "OrderedDict[int, dict[str, Turn]]" = OrderedDict()
    for t in raw_turns:
        if t.role not in ("player", "gm"):
            continue
        bucket = grouped.setdefault(t.turn_no, {})
        bucket[t.role] = t

    # Trim to the most recent `raw_window` complete-or-partial pairs.
    keys = list(grouped.keys())[-raw_window:]

    messages: list[Message] = []
    for turn_no in keys:
        pair = grouped[turn_no]
        player = pair.get("player")
        gm = pair.get("gm")
        if player is not None:
            llm_line = parse_input(player.text).llm_line
            if llm_line:
                messages.append({"role": "user", "content": llm_line})
        if gm is not None:
            messages.append({"role": "assistant", "content": gm.text})

    messages.append({"role": "user", "content": intent.llm_line})
    return system, messages
