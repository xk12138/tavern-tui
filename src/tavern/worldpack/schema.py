"""Schema definitions for a worldpack.

Everything here is a plain dataclass — no third-party validation library,
because we want the validator itself to be dependency-free.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ── field length ceilings (used by W004) ──────────────────────────────────
MAX_FIELD_CHARS = 2000
# Token budget above which we start warning about prompt cost (W005).
MAX_PACK_TOKENS_WARN = 8000
# Anything above this is dangerous — prompt might overflow small models (W005).
MAX_PACK_TOKENS_ERROR_HINT = 16000
# Below this many chars, opening_hook is too short (W008).
MIN_OPENING_HOOK_CHARS = 50
# Above this, honeymoon dominates and player may never see the main plot (W007).
MAX_HONEYMOON_TURNS = 200


@dataclass
class World:
    """Contents of `[world]` in world.toml plus its nested sections."""

    id: str
    name: str
    version: str = "0.0.0"
    author: str = ""
    license: str = ""
    tags: list[str] = field(default_factory=list)
    description: str = ""

    setting: dict[str, Any] = field(default_factory=dict)
    rules: dict[str, Any] = field(default_factory=dict)
    style: dict[str, Any] = field(default_factory=dict)

    factions: list[dict[str, Any]] = field(default_factory=list)
    faction_relations: list[dict[str, Any]] = field(default_factory=list)
    timeline: list[dict[str, Any]] = field(default_factory=list)

    initial_tavern: dict[str, Any] = field(default_factory=dict)
    plot_pacing: dict[str, Any] = field(default_factory=dict)


@dataclass
class NPC:
    """A single NPC card, from `npcs/<id>.toml`."""

    id: str
    name: str
    alias: list[str] = field(default_factory=list)
    card: dict[str, Any] = field(default_factory=dict)
    initial_impression: dict[str, Any] = field(default_factory=dict)
    source_path: Path | None = None


@dataclass
class Location:
    id: str
    name: str
    type: str = ""
    description: dict[str, Any] = field(default_factory=dict)
    notable_places: dict[str, str] = field(default_factory=dict)
    source_path: Path | None = None


@dataclass
class Template:
    """A player-character template offered at world entry."""

    name: str
    tagline: str = ""
    pc: dict[str, Any] = field(default_factory=dict)
    source_path: Path | None = None


@dataclass
class WorldPack:
    """The fully loaded contents of a worldpack directory or single toml."""

    world: World
    npcs: dict[str, NPC] = field(default_factory=dict)
    locations: dict[str, Location] = field(default_factory=dict)
    templates: dict[str, Template] = field(default_factory=dict)
    intro: str | None = None
    path: Path | None = None
    estimated_tokens: int = 0
