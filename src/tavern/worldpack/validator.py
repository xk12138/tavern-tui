"""The rule engine.

`validate_worldpack(path)` composes `loader.load_worldpack()` + a series of
independent rule functions, each returning zero or more `Diagnostic`s.

Rules follow the ID scheme documented in `docs/PRD-worldpack-validate.md`:
  E001..E099  errors (fatal)
  W001..W099  warnings (non-fatal, unless --strict)
  I001..I099  informational (verbose only)
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from tavern.worldpack.diagnostics import Diagnostic, ValidationReport
from tavern.worldpack.loader import LoadError, load_worldpack
from tavern.worldpack.schema import (
    MAX_FIELD_CHARS,
    MAX_HONEYMOON_TURNS,
    MAX_PACK_TOKENS_WARN,
    MIN_OPENING_HOOK_CHARS,
    WorldPack,
)
from tavern.worldpack.tokens import estimate_tokens

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")


def validate_worldpack(path: str | Path) -> ValidationReport:
    """Load + fully validate a worldpack.

    Never raises: I/O problems become error diagnostics on the report.
    """
    result = load_worldpack(path)
    diagnostics: list[Diagnostic] = []

    for err in result.errors:
        diagnostics.append(_load_error_to_diag(err))

    pack = result.pack
    if pack is None:
        return ValidationReport(
            ok=all(d.level != "error" for d in diagnostics),
            diagnostics=diagnostics,
            pack=None,
        )

    # ── run rules ────────────────────────────────────────────────────────
    diagnostics.extend(_rule_world_id_slug(pack))
    diagnostics.extend(_rule_world_semver(pack))
    diagnostics.extend(_rule_required_setting(pack))
    diagnostics.extend(_rule_required_initial_tavern(pack))
    diagnostics.extend(_rule_present_npc_refs(pack))
    diagnostics.extend(_rule_template_hp_sanity(pack))
    diagnostics.extend(_rule_field_length(pack))

    # ── token estimate (rule + attach to pack) ──────────────────────────
    total_tokens = _estimate_pack_tokens(pack)
    pack.estimated_tokens = total_tokens
    diagnostics.extend(_rule_token_budget(total_tokens))

    # ── content-quality warnings ────────────────────────────────────────
    diagnostics.extend(_rule_missing_intro(pack))
    diagnostics.extend(_rule_no_factions(pack))
    diagnostics.extend(_rule_no_timeline(pack))
    diagnostics.extend(_rule_no_templates(pack))
    diagnostics.extend(_rule_honeymoon(pack))
    diagnostics.extend(_rule_opening_hook(pack))
    diagnostics.extend(_rule_npc_card_quality(pack))
    diagnostics.extend(_rule_suggestion_quality(pack))

    # ── informational stats ─────────────────────────────────────────────
    diagnostics.append(_diag_stats(pack))

    ok = not any(d.level == "error" for d in diagnostics)
    return ValidationReport(ok=ok, diagnostics=diagnostics, pack=pack)


# ── translation from loader errors ────────────────────────────────────────


def _load_error_to_diag(err: LoadError) -> Diagnostic:
    return Diagnostic(
        level="error",
        code=err.code,
        message=err.message,
        location=err.location,
        hint=_LOAD_HINTS.get(err.code),
    )


_LOAD_HINTS = {
    "E001": "make sure the path points to a world.toml file or a directory containing one",
    "E002": "add a `world.toml` to the directory or point at the file directly",
    "E003": "check the TOML syntax; the line number above pinpoints the failure",
    "E004": "see WORLD_BUILDING.md §二 for the minimum required fields",
    "E008": "rename the file so its stem matches npc.id, or fix the id",
    "E009": "npc.id must be unique across the pack",
}


# ── individual rules ──────────────────────────────────────────────────────


def _rule_world_id_slug(pack: WorldPack) -> list[Diagnostic]:
    if not _SLUG_RE.match(pack.world.id):
        return [
            Diagnostic(
                level="error",
                code="E005",
                message=f"world.id '{pack.world.id}' is not a valid slug",
                location=_world_location(pack),
                hint="use lowercase letters, digits, dashes, and underscores; must start alphanumeric",
            )
        ]
    return []


def _rule_world_semver(pack: WorldPack) -> list[Diagnostic]:
    if not _SEMVER_RE.match(pack.world.version):
        return [
            Diagnostic(
                level="error",
                code="E006",
                message=f"world.version '{pack.world.version}' is not valid SemVer",
                location=_world_location(pack),
                hint="use MAJOR.MINOR.PATCH, e.g. 0.1.0",
            )
        ]
    return []


def _rule_required_setting(pack: WorldPack) -> list[Diagnostic]:
    if not pack.world.setting:
        return [
            Diagnostic(
                level="error",
                code="E004",
                message="world.setting is required",
                location=_world_location(pack),
                hint="add [world.setting] with at minimum `era` and `tone`",
            )
        ]
    return []


def _rule_required_initial_tavern(pack: WorldPack) -> list[Diagnostic]:
    it = pack.world.initial_tavern
    if not it:
        return [
            Diagnostic(
                level="error",
                code="E004",
                message="world.initial_tavern is required",
                location=_world_location(pack),
                hint="define the opening scene under [world.initial_tavern]",
            )
        ]
    missing = [k for k in ("name", "location", "description") if not it.get(k)]
    if missing:
        return [
            Diagnostic(
                level="error",
                code="E004",
                message=f"world.initial_tavern missing fields: {', '.join(missing)}",
                location=_world_location(pack),
                hint="the opening scene needs at minimum name, location, and description",
            )
        ]
    return []


def _rule_present_npc_refs(pack: WorldPack) -> list[Diagnostic]:
    present = pack.world.initial_tavern.get("present_npcs")
    if not isinstance(present, list):
        return []
    out: list[Diagnostic] = []
    for npc_id in present:
        if not isinstance(npc_id, str):
            continue
        if npc_id not in pack.npcs:
            out.append(
                Diagnostic(
                    level="error",
                    code="E007",
                    message=f"initial_tavern.present_npcs references unknown NPC '{npc_id}'",
                    location=_world_location(pack),
                    hint=f"either add npcs/{npc_id}.toml or remove '{npc_id}' from present_npcs",
                )
            )
    return out


def _rule_template_hp_sanity(pack: WorldPack) -> list[Diagnostic]:
    out: list[Diagnostic] = []
    for tpl in pack.templates.values():
        hp = tpl.pc.get("hp")
        if isinstance(hp, dict):
            cur, mx = hp.get("current"), hp.get("max")
            if (
                isinstance(cur, int)
                and isinstance(mx, int)
                and cur > mx
            ):
                out.append(
                    Diagnostic(
                        level="error",
                        code="E010",
                        message=f"template '{tpl.name}': pc.hp.current ({cur}) > pc.hp.max ({mx})",
                        location=str(tpl.source_path) if tpl.source_path else None,
                        hint="starting HP cannot exceed max HP",
                    )
                )
    return out


def _rule_field_length(pack: WorldPack) -> list[Diagnostic]:
    out: list[Diagnostic] = []

    def _check(text: str, label: str, source: str | None) -> None:
        if isinstance(text, str) and len(text) > MAX_FIELD_CHARS:
            out.append(
                Diagnostic(
                    level="warning",
                    code="W004",
                    message=f"{label} is very long ({len(text)} chars > {MAX_FIELD_CHARS})",
                    location=source,
                    hint="consider splitting into smaller fields; long fields dominate the GM prompt",
                )
            )

    world_loc = _world_location(pack)
    _check(pack.world.description, "world.description", world_loc)
    for key, val in pack.world.setting.items():
        if isinstance(val, str):
            _check(val, f"world.setting.{key}", world_loc)
    for key, val in pack.world.rules.items():
        if isinstance(val, str):
            _check(val, f"world.rules.{key}", world_loc)
    for key, val in pack.world.initial_tavern.items():
        if isinstance(val, str):
            _check(val, f"world.initial_tavern.{key}", world_loc)

    for npc in pack.npcs.values():
        source = str(npc.source_path) if npc.source_path else None
        for key, val in npc.card.items():
            if isinstance(val, str):
                _check(val, f"npc[{npc.id}].card.{key}", source)

    return out


def _estimate_pack_tokens(pack: WorldPack) -> int:
    total = 0
    total += estimate_tokens(pack.world.description)

    def _walk(v: Any) -> None:
        nonlocal total
        if isinstance(v, str):
            total += estimate_tokens(v)
        elif isinstance(v, dict):
            for x in v.values():
                _walk(x)
        elif isinstance(v, list):
            for x in v:
                _walk(x)

    _walk(pack.world.setting)
    _walk(pack.world.rules)
    _walk(pack.world.style)
    _walk(pack.world.factions)
    _walk(pack.world.faction_relations)
    _walk(pack.world.timeline)
    _walk(pack.world.initial_tavern)

    for npc in pack.npcs.values():
        _walk(npc.card)
        _walk(npc.initial_impression)
        _walk(npc.alias)

    for loc in pack.locations.values():
        _walk(loc.description)
        _walk(loc.notable_places)

    for tpl in pack.templates.values():
        _walk(tpl.pc)
        total += estimate_tokens(tpl.tagline)

    if pack.intro:
        total += estimate_tokens(pack.intro)

    return total


def _rule_token_budget(total: int) -> list[Diagnostic]:
    if total > MAX_PACK_TOKENS_WARN:
        return [
            Diagnostic(
                level="warning",
                code="W005",
                message=f"worldpack estimated tokens {total} exceeds {MAX_PACK_TOKENS_WARN} — expensive prompts",
                location=None,
                hint="tighten setting/rules text; big worlds burn tokens on every turn",
            )
        ]
    return []


def _rule_missing_intro(pack: WorldPack) -> list[Diagnostic]:
    has_intro_md = pack.intro is not None and pack.intro.strip()
    has_desc = bool(pack.world.description.strip())
    if not has_intro_md and not has_desc:
        return [
            Diagnostic(
                level="warning",
                code="W001",
                message="no intro.md and no world.description — players get no framing",
                location=_world_location(pack),
                hint="write a short intro.md (~500 chars) to set the tone before play",
            )
        ]
    return []


def _rule_no_factions(pack: WorldPack) -> list[Diagnostic]:
    if not pack.world.factions:
        return [
            Diagnostic(
                level="warning",
                code="W002",
                message="no factions defined",
                location=_world_location(pack),
                hint="[[world.factions]] adds structural conflict; without it the world feels flat",
            )
        ]
    return []


def _rule_no_timeline(pack: WorldPack) -> list[Diagnostic]:
    if not pack.world.timeline:
        return [
            Diagnostic(
                level="warning",
                code="W003",
                message="no timeline events defined",
                location=_world_location(pack),
                hint="[[world.timeline]] gives the world a history — NPCs can reference it",
            )
        ]
    return []


def _rule_no_templates(pack: WorldPack) -> list[Diagnostic]:
    if not pack.templates:
        return [
            Diagnostic(
                level="warning",
                code="W006",
                message="no character templates defined",
                location=_world_location(pack),
                hint="add templates/*.toml so new players have a 3-minute onboarding path",
            )
        ]
    return []


def _rule_honeymoon(pack: WorldPack) -> list[Diagnostic]:
    hm = pack.world.plot_pacing.get("honeymoon_turns")
    if isinstance(hm, int) and hm > MAX_HONEYMOON_TURNS:
        return [
            Diagnostic(
                level="warning",
                code="W007",
                message=f"plot_pacing.honeymoon_turns={hm} is very long",
                location=_world_location(pack),
                hint="players may never reach the main plot; consider < 200",
            )
        ]
    return []


def _rule_opening_hook(pack: WorldPack) -> list[Diagnostic]:
    hook = pack.world.initial_tavern.get("opening_hook", "")
    if not isinstance(hook, str) or len(hook.strip()) < MIN_OPENING_HOOK_CHARS:
        return [
            Diagnostic(
                level="warning",
                code="W008",
                message="initial_tavern.opening_hook is missing or too short",
                location=_world_location(pack),
                hint=f"aim for ≥{MIN_OPENING_HOOK_CHARS} chars; give the player one interactable thing",
            )
        ]
    return []


def _rule_npc_card_quality(pack: WorldPack) -> list[Diagnostic]:
    out: list[Diagnostic] = []
    for npc in pack.npcs.values():
        goals = npc.card.get("goals")
        secrets = npc.card.get("secrets")
        source = str(npc.source_path) if npc.source_path else None
        if not goals:
            out.append(
                Diagnostic(
                    level="warning",
                    code="W009",
                    message=f"npc '{npc.id}' has no goals",
                    location=source,
                    hint="NPCs without goals feel like set dressing; give them at least one desire",
                )
            )
        if not secrets:
            out.append(
                Diagnostic(
                    level="warning",
                    code="W009",
                    message=f"npc '{npc.id}' has no secrets",
                    location=source,
                    hint="secrets are the primary source of dramatic tension",
                )
            )
    return out


def _rule_suggestion_quality(pack: WorldPack) -> list[Diagnostic]:
    raw = pack.world.initial_tavern.get("suggestions")
    if not isinstance(raw, list):
        return []
    out: list[Diagnostic] = []
    for i, item in enumerate(raw):
        where = _world_location(pack)
        if not isinstance(item, dict):
            out.append(
                Diagnostic(
                    level="warning",
                    code="W010",
                    message=f"initial_tavern.suggestions[{i}] is not a table",
                    location=where,
                    hint="each suggestion needs kind = 'say' | 'think' | 'action' and a text",
                )
            )
            continue
        kind = item.get("kind")
        text = item.get("text")
        if kind not in ("say", "think", "action"):
            out.append(
                Diagnostic(
                    level="warning",
                    code="W010",
                    message=(
                        f"initial_tavern.suggestions[{i}].kind = {kind!r} "
                        "is not say | think | action"
                    ),
                    location=where,
                    hint="write player-first-person lines; see WORLD_BUILDING.md §2.6",
                )
            )
        if not isinstance(text, str) or not text.strip():
            out.append(
                Diagnostic(
                    level="warning",
                    code="W010",
                    message=f"initial_tavern.suggestions[{i}].text is missing or empty",
                    location=where,
                    hint="the text is shown verbatim as a selectable player line",
                )
            )
    return out


def _diag_stats(pack: WorldPack) -> Diagnostic:
    return Diagnostic(
        level="info",
        code="I001",
        message=(
            f"world '{pack.world.name}' v{pack.world.version}: "
            f"{len(pack.npcs)} npcs, "
            f"{len(pack.world.factions)} factions, "
            f"{len(pack.world.timeline)} timeline events, "
            f"{len(pack.templates)} templates, "
            f"~{pack.estimated_tokens} tokens"
        ),
        location=None,
    )


def _world_location(pack: WorldPack) -> str:
    if pack.path is None:
        return "world.toml"
    if pack.path.is_file():
        return str(pack.path)
    return str(pack.path / "world.toml")
