"""Install / list / uninstall worldpacks.

All three functions return structured data; the CLI layer is responsible
for rendering. This split keeps a future `--json` flag cheap and makes
these functions callable from tests or embeddings without capturing stdout.
"""

from __future__ import annotations

import datetime as _dt
import shutil
import tarfile
import tempfile
import tomllib
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from tavern.config import ensure_dirs, worlds_dir
from tavern.worldpack.validator import validate_worldpack

INSTALLED_META = ".tavern-installed.toml"

SourceType = Literal["file", "dir", "tar.gz", "zip"]


class InstallError(Exception):
    """Business-level install failure (bad source, id conflict, invalid pack, …).

    CLI catches this to translate into exit code 1 with a friendly message.
    """

    def __init__(self, message: str, code: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass
class InstalledWorld:
    id: str
    name: str
    version: str
    path: Path
    installed_at: str
    source: str
    source_type: str
    estimated_tokens: int


# ── install ──────────────────────────────────────────────────────────────


def install(
    source: Path,
    *,
    force: bool = False,
    skip_validate: bool = False,
) -> InstalledWorld:
    """Install a worldpack from `source` into `<tavern_home>/worlds/<id>/`.

    `source` may be a `world.toml` file, a directory containing one, or a
    `.tar.gz` / `.tgz` / `.zip` archive of a worldpack.
    """
    source = Path(source).expanduser()
    if not source.exists():
        raise InstallError(f"source path does not exist: {source}", "not_found")

    source_type = _detect_source_type(source)

    ensure_dirs()

    with tempfile.TemporaryDirectory(prefix="tavern-install-") as tmpdir:
        staging = Path(tmpdir) / "pack"
        _materialize(source, source_type, staging)

        # After materialization, we should have a directory containing world.toml.
        world_toml = _find_world_toml(staging)
        if world_toml is None:
            raise InstallError(
                "no world.toml found in source",
                "bad_archive",
            )
        pack_root = world_toml.parent

        # Validate before we touch the destination.
        report = validate_worldpack(pack_root)
        if not skip_validate and not report.ok and not force:
            errors = ", ".join(sorted({d.code for d in report.errors}))
            raise InstallError(
                f"worldpack failed validation ({errors}); "
                f"fix errors or pass --force to install anyway",
                "validation",
            )

        world_id = report.pack.world.id if report.pack else _peek_world_id(world_toml)
        if not world_id:
            raise InstallError("cannot determine world.id", "validation")

        dest = worlds_dir() / world_id
        if dest.exists():
            if not force:
                existing_ver = _peek_world_version(dest / "world.toml") or "?"
                raise InstallError(
                    f"world '{world_id}' is already installed (v{existing_ver}); "
                    f"pass --force to overwrite",
                    "exists",
                )
            shutil.rmtree(dest)

        shutil.copytree(pack_root, dest)

        installed_at = _dt.datetime.now(tz=_dt.timezone.utc).replace(
            microsecond=0
        ).isoformat().replace("+00:00", "Z")
        _write_meta(
            dest,
            installed_at=installed_at,
            source=str(source.resolve()),
            source_type=source_type,
        )

        return InstalledWorld(
            id=world_id,
            name=report.pack.world.name if report.pack else world_id,
            version=report.pack.world.version if report.pack else "0.0.0",
            path=dest,
            installed_at=installed_at,
            source=str(source.resolve()),
            source_type=source_type,
            estimated_tokens=(
                report.pack.estimated_tokens if report.pack else 0
            ),
        )


# ── list ─────────────────────────────────────────────────────────────────


def list_installed() -> list[InstalledWorld]:
    """Enumerate installed worldpacks in stable id order.

    Directories that don't parse as valid worldpacks are silently skipped
    (they may be junk / half-finished manual copies) — validation errors
    surface during `tavern validate`, not here.
    """
    root = worlds_dir()
    if not root.is_dir():
        return []
    out: list[InstalledWorld] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        world_toml = child / "world.toml"
        if not world_toml.is_file():
            continue
        try:
            with world_toml.open("rb") as fh:
                data = tomllib.load(fh)
        except tomllib.TOMLDecodeError:
            continue
        w = data.get("world", {})
        meta = _read_meta(child) or {}
        # Best-effort token estimate from validator (cheap enough).
        try:
            report = validate_worldpack(child)
            tokens = report.pack.estimated_tokens if report.pack else 0
        except Exception:
            tokens = 0
        out.append(
            InstalledWorld(
                id=str(w.get("id", child.name)),
                name=str(w.get("name", child.name)),
                version=str(w.get("version", "0.0.0")),
                path=child,
                installed_at=str(meta.get("installed_at", "?")),
                source=str(meta.get("source", "?")),
                source_type=str(meta.get("source_type", "?")),
                estimated_tokens=tokens,
            )
        )
    return out


# ── uninstall ────────────────────────────────────────────────────────────


def uninstall(world_id: str) -> InstalledWorld:
    """Remove the worldpack directory named `world_id`.

    Returns a snapshot of the removed world (for user-facing confirmation).
    """
    dest = worlds_dir() / world_id
    if not dest.is_dir():
        raise InstallError(f"no installed world with id '{world_id}'", "not_found")

    world_toml = dest / "world.toml"
    snapshot_name = world_id
    snapshot_version = "?"
    if world_toml.is_file():
        try:
            with world_toml.open("rb") as fh:
                data = tomllib.load(fh)
            w = data.get("world", {})
            snapshot_name = str(w.get("name", world_id))
            snapshot_version = str(w.get("version", "?"))
        except tomllib.TOMLDecodeError:
            pass

    meta = _read_meta(dest) or {}
    snapshot = InstalledWorld(
        id=world_id,
        name=snapshot_name,
        version=snapshot_version,
        path=dest,
        installed_at=str(meta.get("installed_at", "?")),
        source=str(meta.get("source", "?")),
        source_type=str(meta.get("source_type", "?")),
        estimated_tokens=0,
    )
    shutil.rmtree(dest)
    return snapshot


# ── helpers ──────────────────────────────────────────────────────────────


def _detect_source_type(path: Path) -> SourceType:
    if path.is_dir():
        return "dir"
    name = path.name.lower()
    if name.endswith((".tar.gz", ".tgz")):
        return "tar.gz"
    if name.endswith(".zip"):
        return "zip"
    if name.endswith(".toml"):
        return "file"
    raise InstallError(
        f"unsupported source type: {path.name}; expected .toml, directory, .tar.gz, or .zip",
        "bad_archive",
    )


def _materialize(source: Path, source_type: SourceType, staging: Path) -> None:
    """Put a worldpack-shaped tree at `staging`."""
    staging.mkdir(parents=True, exist_ok=True)
    if source_type == "dir":
        shutil.copytree(source, staging, dirs_exist_ok=True)
    elif source_type == "file":
        shutil.copy2(source, staging / "world.toml")
    elif source_type == "tar.gz":
        _safe_extract_tar(source, staging)
    elif source_type == "zip":
        _safe_extract_zip(source, staging)


def _safe_extract_tar(archive: Path, dest: Path) -> None:
    try:
        with tarfile.open(archive, "r:*") as tf:
            for member in tf.getmembers():
                _guard_member_path(member.name, member.issym() or member.islnk())
            # data filter (Python 3.12+) blocks unsafe absolute paths and links.
            try:
                tf.extractall(dest, filter="data")  # type: ignore[arg-type]
            except TypeError:
                # Older Python fallback: we already did manual guard above.
                tf.extractall(dest)
    except tarfile.TarError as exc:
        raise InstallError(f"cannot extract tar archive: {exc}", "bad_archive")


def _safe_extract_zip(archive: Path, dest: Path) -> None:
    try:
        with zipfile.ZipFile(archive) as zf:
            for name in zf.namelist():
                _guard_member_path(name, is_link=False)
            zf.extractall(dest)
    except zipfile.BadZipFile as exc:
        raise InstallError(f"cannot extract zip archive: {exc}", "bad_archive")


def _guard_member_path(name: str, is_link: bool) -> None:
    """Reject archive members that would escape the staging directory.

    Blocks zip-slip (`../etc/passwd`) and links (symlinks/hardlinks can point
    anywhere on disk after extraction).
    """
    if is_link:
        raise InstallError(
            f"archive contains symlink/hardlink '{name}'; refusing to extract",
            "bad_archive",
        )
    # Normalize and check: no leading /, no .. components after normalization
    normalized = Path(name)
    if normalized.is_absolute():
        raise InstallError(
            f"archive contains absolute path '{name}'; refusing to extract",
            "bad_archive",
        )
    parts = normalized.parts
    if ".." in parts:
        raise InstallError(
            f"archive contains parent-traversal path '{name}'; refusing to extract",
            "bad_archive",
        )


def _find_world_toml(root: Path) -> Path | None:
    """Locate world.toml, walking into a single top-level subdir if needed.

    Handles the common `tar czf out.tar.gz my-world/` case where extraction
    yields `staging/my-world/world.toml`.
    """
    direct = root / "world.toml"
    if direct.is_file():
        return direct

    # Any depth: check one level down (typical archive shape).
    children = [c for c in root.iterdir() if c.is_dir()]
    if len(children) == 1:
        candidate = children[0] / "world.toml"
        if candidate.is_file():
            return candidate

    # Last resort: shallow rglob (avoid deep scanning).
    for p in root.glob("*/world.toml"):
        if p.is_file():
            return p
    return None


def _peek_world_id(world_toml: Path) -> str | None:
    data = _peek_world_toml(world_toml)
    if data is None:
        return None
    wid = data.get("id")
    return wid if isinstance(wid, str) and wid else None


def _peek_world_version(world_toml: Path) -> str | None:
    data = _peek_world_toml(world_toml)
    if data is None:
        return None
    ver = data.get("version")
    return str(ver) if ver else None


def _peek_world_toml(world_toml: Path) -> dict | None:
    try:
        with world_toml.open("rb") as fh:
            data = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        return None
    w = data.get("world")
    return w if isinstance(w, dict) else None


def _read_meta(pack_dir: Path) -> dict | None:
    meta_path = pack_dir / INSTALLED_META
    if not meta_path.is_file():
        return None
    try:
        with meta_path.open("rb") as fh:
            data = tomllib.load(fh)
    except tomllib.TOMLDecodeError:
        return None
    return data.get("install") if isinstance(data.get("install"), dict) else None


def _write_meta(
    pack_dir: Path,
    *,
    installed_at: str,
    source: str,
    source_type: str,
) -> None:
    from tavern import __version__

    meta_path = pack_dir / INSTALLED_META
    content = (
        "[install]\n"
        f'installed_at = "{installed_at}"\n'
        f'source       = "{_toml_escape(source)}"\n'
        f'source_type  = "{source_type}"\n'
        f'tavern_ver   = "{__version__}"\n'
    )
    meta_path.write_text(content, encoding="utf-8")


def _toml_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')
