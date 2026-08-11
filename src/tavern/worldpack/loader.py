"""Load a worldpack from disk.

A worldpack is either:
  - a single `world.toml` file, or
  - a directory containing `world.toml` and optionally
    `npcs/*.toml`, `locations/*.toml`, `templates/*.toml`, `intro.md`.

The loader gathers everything into a `WorldPack` and also records any
structural problems (bad TOML, wrong npc.id, missing files) via the
`LoadError` list on the returned `_LoadResult`. The validator translates
these into user-facing Diagnostics — the loader itself is layout-only.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tavern.worldpack.schema import (
    NPC,
    Location,
    Template,
    World,
    WorldPack,
)


@dataclass
class LoadError:
    """A structural failure the loader encountered.

    We separate this from `Diagnostic` because the loader has no opinions
    about severity — a broken NPC file is just a fact; the validator decides
    whether it's an error or a warning.
    """

    code: str
    message: str
    location: str | None = None


@dataclass
class _LoadResult:
    pack: WorldPack | None
    errors: list[LoadError] = field(default_factory=list)


def load_worldpack(path: str | Path) -> _LoadResult:
    """Read a worldpack from disk. Never raises for file-content issues.

    Only raises for hard I/O errors (path doesn't exist / can't be read) —
    those become CLI exit code 2, not validation failures.
    """
    p = Path(path)
    if not p.exists():
        return _LoadResult(
            pack=None,
            errors=[LoadError("E001", f"path does not exist: {p}", str(p))],
        )

    if p.is_file():
        return _load_single_file(p)
    if p.is_dir():
        return _load_directory(p)

    return _LoadResult(
        pack=None,
        errors=[LoadError("E001", f"path is neither file nor directory: {p}", str(p))],
    )


# ── single-file mode ──────────────────────────────────────────────────────


def _load_single_file(p: Path) -> _LoadResult:
    parsed, err = _parse_toml(p)
    if err:
        return _LoadResult(pack=None, errors=[err])

    world, world_errors = _extract_world(parsed, p)
    if world is None:
        return _LoadResult(pack=None, errors=world_errors)

    pack = WorldPack(world=world, path=p)
    return _LoadResult(pack=pack, errors=world_errors)


# ── directory mode ────────────────────────────────────────────────────────


def _load_directory(root: Path) -> _LoadResult:
    world_toml = root / "world.toml"
    if not world_toml.exists():
        return _LoadResult(
            pack=None,
            errors=[
                LoadError("E002", "world.toml not found in directory", str(root)),
            ],
        )

    parsed, err = _parse_toml(world_toml)
    if err:
        return _LoadResult(pack=None, errors=[err])

    world, world_errors = _extract_world(parsed, world_toml)
    if world is None:
        return _LoadResult(pack=None, errors=world_errors)

    pack = WorldPack(world=world, path=root)
    errors: list[LoadError] = list(world_errors)

    # NPCs
    npcs_dir = root / "npcs"
    if npcs_dir.is_dir():
        for f in sorted(npcs_dir.glob("*.toml")):
            npc, e = _load_npc(f)
            if e:
                errors.extend(e)
            if npc:
                if npc.id in pack.npcs:
                    errors.append(
                        LoadError(
                            "E009",
                            f"duplicate npc id: {npc.id}",
                            str(f),
                        )
                    )
                else:
                    pack.npcs[npc.id] = npc

    # Locations
    locs_dir = root / "locations"
    if locs_dir.is_dir():
        for f in sorted(locs_dir.glob("*.toml")):
            loc, e = _load_location(f)
            if e:
                errors.extend(e)
            if loc:
                pack.locations[loc.id] = loc

    # Templates
    tpl_dir = root / "templates"
    if tpl_dir.is_dir():
        for f in sorted(tpl_dir.glob("*.toml")):
            tpl, e = _load_template(f)
            if e:
                errors.extend(e)
            if tpl:
                pack.templates[tpl.name] = tpl

    # Intro
    intro_md = root / "intro.md"
    if intro_md.is_file():
        try:
            pack.intro = intro_md.read_text(encoding="utf-8")
        except OSError as exc:
            errors.append(
                LoadError("E003", f"cannot read intro.md: {exc}", str(intro_md))
            )

    return _LoadResult(pack=pack, errors=errors)


# ── helpers ───────────────────────────────────────────────────────────────


def _parse_toml(p: Path) -> tuple[dict[str, Any] | None, LoadError | None]:
    try:
        with p.open("rb") as fh:
            return tomllib.load(fh), None
    except tomllib.TOMLDecodeError as exc:
        line = getattr(exc, "lineno", None)
        loc = f"{p}:{line}" if line else str(p)
        return None, LoadError("E003", f"invalid TOML: {exc}", loc)
    except OSError as exc:
        return None, LoadError("E003", f"cannot read file: {exc}", str(p))


def _extract_world(
    data: dict[str, Any], source: Path
) -> tuple[World | None, list[LoadError]]:
    """Build a `World` from the top-level `[world]` table.

    Returns (None, errors) if fatally malformed (E004 for id/name), otherwise
    returns (world, []) with best-effort field coercion. Structural refinements
    (missing setting section, bad slug, etc.) are handled by the validator.
    """
    w = data.get("world")
    if not isinstance(w, dict):
        return None, [
            LoadError(
                "E004",
                "missing top-level [world] table",
                str(source),
            )
        ]

    wid = w.get("id")
    name = w.get("name")
    errors: list[LoadError] = []

    if not isinstance(wid, str) or not wid:
        errors.append(LoadError("E004", "world.id is required", str(source)))
    if not isinstance(name, str) or not name:
        errors.append(LoadError("E004", "world.name is required", str(source)))

    # If we can't even name the world, don't try to build one — most other
    # checks would be dominated by cascading errors.
    if errors:
        return None, errors

    world = World(
        id=wid,
        name=name,
        version=str(w.get("version", "0.0.0")),
        author=str(w.get("author", "")),
        license=str(w.get("license", "")),
        tags=list(w.get("tags", [])) if isinstance(w.get("tags"), list) else [],
        description=str(w.get("description", "")),
        setting=_as_dict(w.get("setting")),
        rules=_as_dict(w.get("rules")),
        style=_as_dict(w.get("style")),
        factions=_as_list_of_dicts(w.get("factions")),
        faction_relations=_as_list_of_dicts(w.get("faction_relations")),
        timeline=_as_list_of_dicts(w.get("timeline")),
        initial_tavern=_as_dict(w.get("initial_tavern")),
        plot_pacing=_as_dict(w.get("plot_pacing")),
    )
    return world, errors


def _as_dict(v: Any) -> dict[str, Any]:
    return v if isinstance(v, dict) else {}


def _as_list_of_dicts(v: Any) -> list[dict[str, Any]]:
    if not isinstance(v, list):
        return []
    return [item for item in v if isinstance(item, dict)]


def _load_npc(p: Path) -> tuple[NPC | None, list[LoadError]]:
    data, err = _parse_toml(p)
    if err:
        return None, [err]
    if not isinstance(data, dict):
        return None, []

    section = data.get("npc")
    if not isinstance(section, dict):
        return None, [LoadError("E004", "missing [npc] section", str(p))]

    npc_id = section.get("id")
    name = section.get("name")
    errors: list[LoadError] = []

    if not isinstance(npc_id, str) or not npc_id:
        errors.append(LoadError("E004", "npc.id is required", str(p)))
    if not isinstance(name, str) or not name:
        errors.append(LoadError("E004", "npc.name is required", str(p)))
    if errors:
        return None, errors

    # E008: filename should match id
    if p.stem != npc_id:
        errors.append(
            LoadError(
                "E008",
                f"filename '{p.stem}' does not match npc.id '{npc_id}'",
                str(p),
            )
        )

    npc = NPC(
        id=npc_id,
        name=name,
        alias=list(section.get("alias", [])) if isinstance(section.get("alias"), list) else [],
        card=_as_dict(section.get("card")),
        initial_impression=_as_dict(section.get("initial_impression")),
        source_path=p,
    )
    return npc, errors


def _load_location(p: Path) -> tuple[Location | None, list[LoadError]]:
    data, err = _parse_toml(p)
    if err:
        return None, [err]

    section = data.get("location")
    if not isinstance(section, dict):
        return None, [LoadError("E004", "missing [location] section", str(p))]

    lid = section.get("id")
    name = section.get("name")
    if not isinstance(lid, str) or not lid or not isinstance(name, str) or not name:
        return None, [LoadError("E004", "location.id and location.name are required", str(p))]

    return Location(
        id=lid,
        name=name,
        type=str(section.get("type", "")),
        description=_as_dict(section.get("description")),
        notable_places=_as_dict(section.get("notable_places")),
        source_path=p,
    ), []


def _load_template(p: Path) -> tuple[Template | None, list[LoadError]]:
    data, err = _parse_toml(p)
    if err:
        return None, [err]

    section = data.get("template")
    if not isinstance(section, dict):
        return None, [LoadError("E004", "missing [template] section", str(p))]

    name = section.get("name")
    if not isinstance(name, str) or not name:
        return None, [LoadError("E004", "template.name is required", str(p))]

    return Template(
        name=name,
        tagline=str(section.get("tagline", "")),
        pc=_as_dict(section.get("pc")),
        source_path=p,
    ), []
