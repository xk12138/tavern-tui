"""Renderers for observation commands: /where /who /inv /status /relations.

These are pure functions that take (pack, save) and return a string. The CLI
layer only calls them and prints the result — this keeps the render logic
easy to unit-test.

Security: /who deliberately hides `goals` and `secrets` from NPC cards.
Those are GM-side information; leaking them would spoil the story. There's
an explicit test that guards against regressions here.
"""

from __future__ import annotations

from typing import Any

from tavern.save import Save
from tavern.worldpack.schema import NPC, WorldPack


def render_where(pack: WorldPack, save: Save) -> str:
    """Show current scene: prefer save.state.current_scene, else initial_tavern."""
    state = save.state
    lines: list[str] = []

    scene_name: str
    location: str
    description: str
    if state.current_scene:
        scene_name = state.current_scene
        location = ""
        description = ""
    else:
        it = pack.world.initial_tavern
        scene_name = str(it.get("name", "?"))
        location = str(it.get("location", ""))
        description = str(it.get("description", "")).strip()

    lines.append(f"Current scene: {scene_name}")
    if location:
        lines.append(f"Location: {location}")
    if description:
        lines.append("Description:")
        for para in description.splitlines():
            para = para.strip()
            if para:
                lines.append(f"  {para}")

    time_label = state.time_of_day or f"(turn {state.turn_count})"
    lines.append(f"Time: {time_label}")
    return "\n".join(lines)


def render_who(pack: WorldPack, save: Save, arg: str = "") -> str:
    """List present NPCs, or describe one if `arg` names them."""
    arg = arg.strip()

    if not arg:
        return _render_who_list(pack)

    npc = _find_npc(pack, arg)
    if npc is None:
        return f"no such NPC '{arg}' in this world"
    return _render_npc_details(npc)


def _render_who_list(pack: WorldPack) -> str:
    present = pack.world.initial_tavern.get("present_npcs", [])
    if not isinstance(present, list) or not present:
        return "(no NPCs listed for this scene)"

    lines = ["NPCs in this scene:"]
    for npc_id in present:
        if not isinstance(npc_id, str):
            continue
        npc = pack.npcs.get(npc_id)
        if npc is None:
            # Referenced but not present in pack.npcs — surface the id anyway.
            lines.append(f"  - ({npc_id}) — (details unavailable)")
            continue
        impression = str(npc.initial_impression.get("description", "")).strip()
        blurb = _short(impression, 80) if impression else "(no impression noted)"
        lines.append(f"  - {npc.name} ({npc.id}) — {blurb}")
    return "\n".join(lines)


def _render_npc_details(npc: NPC) -> str:
    """Public NPC info only — never emit goals or secrets."""
    lines = [f"{npc.name} ({npc.id})"]

    if npc.alias:
        lines.append(f"Also known as: {', '.join(npc.alias)}")

    appearance = str(npc.card.get("appearance", "")).strip()
    if appearance:
        lines.append(f"Appearance: {appearance}")

    speech = str(npc.card.get("speech_style", "")).strip()
    if speech:
        lines.append(f"Manner of speech: {speech}")

    impression = str(npc.initial_impression.get("description", "")).strip()
    if impression:
        lines.append("")
        lines.append("Your impression:")
        for line in impression.splitlines():
            stripped = line.strip()
            if stripped:
                lines.append(f"  {stripped}")

    return "\n".join(lines)


def _find_npc(pack: WorldPack, needle: str) -> NPC | None:
    """Match by id, name, or alias — case-insensitive exact match."""
    lower = needle.lower()
    if needle in pack.npcs:
        return pack.npcs[needle]
    for npc in pack.npcs.values():
        if npc.id.lower() == lower:
            return npc
        if npc.name.lower() == lower:
            return npc
        for alias in npc.alias:
            if isinstance(alias, str) and alias.lower() == lower:
                return npc
    return None


# ── /inv /status /relations ──────────────────────────────────────────────


_UNTRACKED = "(not tracked yet — Extractor coming in a future release)"


def render_inv(pack: WorldPack, save: Save) -> str:
    return f"Inventory:\n  {_UNTRACKED}"


def render_status(pack: WorldPack, save: Save) -> str:
    state = save.state
    lines = [
        "Character status:",
        f"  turn:  {state.turn_count}",
        f"  day:   {state.day}",
        f"  time:  {state.time_of_day or '(not set)'}",
        f"  scene: {state.current_scene or '(not set)'}",
        "",
        "HP, attributes, and inventory aren't tracked yet — "
        "Extractor coming in a future release.",
    ]
    return "\n".join(lines)


def render_relations(pack: WorldPack, save: Save) -> str:
    return f"Relationships:\n  {_UNTRACKED}"


# ── helpers ──────────────────────────────────────────────────────────────


def _short(s: str, limit: int) -> str:
    s = " ".join(s.split())   # collapse whitespace
    if len(s) <= limit:
        return s
    return s[: limit - 1] + "…"
