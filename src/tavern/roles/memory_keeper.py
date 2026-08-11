"""Memory Keeper — the L2 (scene summary) compressor.

Called by the orchestrator every 10 turns starting at turn 15. Given the
prior summary (if any) and the raw turns since it was written, produces a
new ~200-token summary that REPLACES the old one. The result is stored in
`scene_summary` (singleton) and prepended to the Narrator's system prompt
on every subsequent turn.

Design choices:
  * Single function, no class — matches how `export/novel.py` treats the
    provider. A stateful class would just be a call-convention.
  * The summary target is ~200 tokens (DESIGN.md §五 L2). We pass
    max_tokens=400 to give the model headroom without wasting budget.
  * Transcript uses "Player:" / "GM:" prefixes rather than replaying
    `llm_line` shapes — we're summarising, not re-narrating.
"""

from __future__ import annotations

from tavern.llm.base import LLMProvider
from tavern.save.store import Turn
from tavern.worldpack.schema import WorldPack


_SYSTEM_PROMPT_TEMPLATE = """\
You are the Memory Keeper for a story set in the world "{world_name}".

Your job is to distil the transcript below into a dense narrative summary of
about 200 tokens. Write in third person, past tense.

Preserve:
  * cast present in recent scenes (who they are, how they relate)
  * current location and how the player got there
  * unresolved tensions, promises, and open questions
  * injuries, status changes, items acquired or lost
  * key decisions the player made and their fallout

Drop:
  * prose flourishes, sensory description that isn't load-bearing
  * second-person voice — this is a summary for the GM, not for the player
  * redundant beats already implied by earlier events

If a prior summary is given, CONTINUE from it — do not restart the narrative
or repeat facts it already covers. Merge the new events into the same story.

Return only the summary text, no preamble."""


def _format_transcript(raw_turns: list[Turn]) -> str:
    """Render a list of stored turns as a plain Player/GM transcript."""
    lines: list[str] = []
    for turn in raw_turns:
        if turn.role == "player":
            lines.append(f"Player: {turn.text}")
        elif turn.role == "gm":
            lines.append(f"GM: {turn.text}")
        # System rows (opening hook at turn_no=0) are skipped — they're
        # already implied by the world setup, no summary value.
    return "\n".join(lines)


def compress(
    provider: LLMProvider,
    prior_summary: str | None,
    raw_turns: list[Turn],
    pack: WorldPack,
) -> str:
    """Produce a new scene summary. Returns the summary text (stripped).

    Raises whatever the underlying provider raises (LLMError family) — the
    caller decides whether a compression failure should abort the turn or
    just be logged.
    """
    system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(world_name=pack.world.name)
    prior_block = prior_summary or "(none — this is the first summary)"
    user_prompt = (
        f"Prior summary:\n{prior_block}\n\n"
        f"New transcript:\n{_format_transcript(raw_turns)}\n\n"
        "Write the updated summary now."
    )
    reply = provider.complete(user_prompt, system=system_prompt, max_tokens=400)
    return reply.strip()
