"""Save file: SQLite-backed scene log + world state.

Design notes:
  * Every write is its own transaction (autocommit disabled at connect,
    we open BEGIN…COMMIT via `with self._conn:`) — SQLite is fast enough
    that batching would only complicate the failure story.
  * We store `player` and `gm` as separate rows sharing a `turn_no`. This
    matches DESIGN.md §六 and keeps rewind/export straightforward.
  * copy_to uses SQLite's built-in `Connection.backup()` for atomic copy.
"""

from __future__ import annotations

import datetime as _dt
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from tavern.config import tavern_home
from tavern.save.schema import DDL, SCHEMA_VERSION, VALID_ROLES


# ── errors ───────────────────────────────────────────────────────────────


class SaveError(Exception):
    """Base for all save-file failures."""


class SaveNameError(SaveError):
    """Save name is illegal (bad chars, too long, empty)."""


class SaveNotFoundError(SaveError):
    """No save with the given name exists."""


class SaveExistsError(SaveError):
    """Refusing to overwrite an existing save."""


class SchemaMismatchError(SaveError):
    """The save file was written by a different schema version."""


# ── name / path helpers ──────────────────────────────────────────────────


_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}$")


def _validate_name(name: str) -> None:
    if not isinstance(name, str) or not _NAME_RE.match(name):
        raise SaveNameError(
            f"invalid save name {name!r}: "
            "must start with a letter/digit and contain only "
            "letters, digits, '.', '_', '-' (max 64 chars)"
        )


def saves_dir() -> Path:
    return tavern_home() / "saves"


def save_path(name: str) -> Path:
    """Resolve a save name to its `.db` path. Validates the name."""
    _validate_name(name)
    return saves_dir() / f"{name}.db"


def _now_iso() -> str:
    return (
        _dt.datetime.now(tz=_dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


# ── data classes ─────────────────────────────────────────────────────────


@dataclass
class SaveState:
    turn_count: int = 0
    current_scene: str = ""
    day: int = 1
    time_of_day: str = ""


@dataclass
class Turn:
    id: int
    turn_no: int
    role: str
    text: str
    created_at: str


@dataclass
class SaveSummary:
    name: str
    path: Path
    world_id: str
    turn_count: int
    updated_at: str


@dataclass
class SceneSummary:
    """L2 compressed memory: a running summary that replaces itself on every
    Memory Keeper pass. Singleton at id=1.
    """
    summary_text: str
    covered_up_to_turn: int
    generated_at: str


# ── the main class ───────────────────────────────────────────────────────


class Save:
    def __init__(self, path: Path):
        self._path = path
        self._conn: sqlite3.Connection | None = None

    # ── construction ────────────────────────────────────────────────

    @classmethod
    def new(cls, name: str, world_id: str) -> "Save":
        """Create a fresh save. Raises SaveExistsError if it already exists."""
        p = save_path(name)
        if p.exists():
            raise SaveExistsError(f"save '{name}' already exists at {p}")
        p.parent.mkdir(parents=True, exist_ok=True)

        save = cls(p)
        save._connect()
        save._create_schema()
        save._insert_meta(world_id=world_id, save_name=name)
        save._insert_state()
        return save

    @classmethod
    def open(cls, name: str) -> "Save":
        """Open an existing save. Raises SaveNotFoundError / SchemaMismatchError."""
        p = save_path(name)
        if not p.exists():
            raise SaveNotFoundError(f"save '{name}' not found at {p}")
        save = cls(p)
        save._connect()
        save._check_schema()
        return save

    # ── connection lifecycle ────────────────────────────────────────

    def _connect(self) -> None:
        # isolation_level=None gives manual transaction control via `with`.
        self._conn = sqlite3.connect(str(self._path), isolation_level=None)
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.row_factory = sqlite3.Row

    def close(self) -> None:
        """Close the connection. Idempotent."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "Save":
        return self

    def __exit__(self, *args) -> None:
        self.close()

    # ── properties ──────────────────────────────────────────────────

    @property
    def path(self) -> Path:
        return self._path

    @property
    def name(self) -> str:
        row = self._one("SELECT save_name FROM save_meta WHERE id = 1")
        return row["save_name"] if row else self._path.stem

    @property
    def world_id(self) -> str:
        row = self._one("SELECT world_id FROM save_meta WHERE id = 1")
        return row["world_id"] if row else ""

    @property
    def state(self) -> SaveState:
        row = self._one("SELECT * FROM world_state WHERE id = 1")
        if not row:
            return SaveState()
        return SaveState(
            turn_count=row["turn_count"],
            current_scene=row["current_scene"],
            day=row["day"],
            time_of_day=row["time_of_day"],
        )

    # ── writes ──────────────────────────────────────────────────────

    def append_turn(self, role: str, text: str, *, turn_no: int) -> Turn:
        if role not in VALID_ROLES:
            raise SaveError(f"invalid role {role!r}; expected one of {sorted(VALID_ROLES)}")
        created_at = _now_iso()
        with self._tx() as conn:
            cur = conn.execute(
                "INSERT INTO scene_log (turn_no, role, text, created_at) VALUES (?,?,?,?)",
                (turn_no, role, text, created_at),
            )
            new_id = cur.lastrowid
        return Turn(
            id=new_id if new_id is not None else -1,
            turn_no=turn_no,
            role=role,
            text=text,
            created_at=created_at,
        )

    def update_state(
        self,
        *,
        turn_count: int | None = None,
        current_scene: str | None = None,
        day: int | None = None,
        time_of_day: str | None = None,
    ) -> None:
        sets = []
        params: list = []
        if turn_count is not None:
            sets.append("turn_count = ?")
            params.append(turn_count)
        if current_scene is not None:
            sets.append("current_scene = ?")
            params.append(current_scene)
        if day is not None:
            sets.append("day = ?")
            params.append(day)
        if time_of_day is not None:
            sets.append("time_of_day = ?")
            params.append(time_of_day)
        if not sets:
            return
        sets.append("updated_at = ?")
        params.append(_now_iso())
        with self._tx() as conn:
            conn.execute(
                f"UPDATE world_state SET {', '.join(sets)} WHERE id = 1",
                params,
            )

    def rewind(self, pairs: int = 1) -> int:
        """Delete the last `pairs` logical turns.

        Returns the number of `scene_log` rows deleted.
        """
        if pairs <= 0:
            return 0
        state = self.state
        if state.turn_count == 0:
            return 0
        keep_upto = max(0, state.turn_count - pairs)
        with self._tx() as conn:
            cur = conn.execute(
                "DELETE FROM scene_log WHERE turn_no > ?",
                (keep_upto,),
            )
            deleted = cur.rowcount
            conn.execute(
                "UPDATE world_state SET turn_count = ?, updated_at = ? WHERE id = 1",
                (keep_upto, _now_iso()),
            )
        return deleted

    # ── reads ───────────────────────────────────────────────────────

    def turns(self, limit: int | None = None) -> list[Turn]:
        sql = "SELECT id, turn_no, role, text, created_at FROM scene_log ORDER BY id ASC"
        params: tuple = ()
        if limit is not None:
            sql += " LIMIT ?"
            params = (limit,)
        rows = self._all(sql, params)
        return [
            Turn(
                id=r["id"], turn_no=r["turn_no"], role=r["role"],
                text=r["text"], created_at=r["created_at"],
            )
            for r in rows
        ]

    def recent_turns(self, n: int) -> list[Turn]:
        """Return the last `n` turns (still in chronological order)."""
        rows = self._all(
            "SELECT id, turn_no, role, text, created_at "
            "FROM (SELECT * FROM scene_log ORDER BY id DESC LIMIT ?) "
            "ORDER BY id ASC",
            (n,),
        )
        return [
            Turn(
                id=r["id"], turn_no=r["turn_no"], role=r["role"],
                text=r["text"], created_at=r["created_at"],
            )
            for r in rows
        ]

    def turns_after(self, turn_no: int) -> list[Turn]:
        """Return turns with turn_no strictly greater than the given cutoff.

        Used by the context assembler to fetch everything past the summary's
        `covered_up_to_turn`. Chronological order.
        """
        rows = self._all(
            "SELECT id, turn_no, role, text, created_at "
            "FROM scene_log WHERE turn_no > ? ORDER BY id ASC",
            (turn_no,),
        )
        return [
            Turn(
                id=r["id"], turn_no=r["turn_no"], role=r["role"],
                text=r["text"], created_at=r["created_at"],
            )
            for r in rows
        ]

    # ── scene summary (L2 memory) ───────────────────────────────────

    def summary(self) -> SceneSummary | None:
        row = self._one(
            "SELECT summary_text, covered_up_to_turn, generated_at "
            "FROM scene_summary WHERE id = 1"
        )
        if row is None:
            return None
        return SceneSummary(
            summary_text=row["summary_text"],
            covered_up_to_turn=row["covered_up_to_turn"],
            generated_at=row["generated_at"],
        )

    def set_summary(self, text: str, *, covered_up_to_turn: int) -> None:
        """Overwrite the singleton scene_summary row (INSERT-or-REPLACE)."""
        now = _now_iso()
        with self._tx() as conn:
            conn.execute(
                "INSERT INTO scene_summary "
                "(id, summary_text, covered_up_to_turn, generated_at) "
                "VALUES (1, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET "
                "summary_text = excluded.summary_text, "
                "covered_up_to_turn = excluded.covered_up_to_turn, "
                "generated_at = excluded.generated_at",
                (text, covered_up_to_turn, now),
            )

    # ── copy ────────────────────────────────────────────────────────

    def copy_to(self, new_name: str) -> "Save":
        """Copy this save to `new_name` and return a Save opened on the copy.

        Uses SQLite's built-in backup API for atomic online copy — safe even
        with active writers on the source (WAL mode).
        """
        dst_path = save_path(new_name)
        if dst_path.exists():
            raise SaveExistsError(f"save '{new_name}' already exists at {dst_path}")
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        # Ensure the source has a live connection.
        if self._conn is None:
            raise SaveError("cannot copy a closed save")

        dst_conn = sqlite3.connect(str(dst_path), isolation_level=None)
        try:
            self._conn.backup(dst_conn)
            # Rename inside the copy so it reflects the new save_name.
            dst_conn.execute(
                "UPDATE save_meta SET save_name = ? WHERE id = 1",
                (new_name,),
            )
        finally:
            dst_conn.close()

        return Save.open(new_name)

    # ── internals ───────────────────────────────────────────────────

    def _tx(self) -> sqlite3.Connection:
        """Return the underlying connection, expected to be used in `with`.

        We rely on `sqlite3.Connection.__enter__/__exit__` for begin/commit
        semantics — with `isolation_level=None`, `with conn:` still commits
        on success and rollbacks on exception.
        """
        assert self._conn is not None, "connection is closed"
        return self._conn

    def _one(self, sql: str, params: Iterable = ()) -> sqlite3.Row | None:
        assert self._conn is not None
        cur = self._conn.execute(sql, tuple(params))
        return cur.fetchone()

    def _all(self, sql: str, params: Iterable = ()) -> list[sqlite3.Row]:
        assert self._conn is not None
        cur = self._conn.execute(sql, tuple(params))
        return list(cur.fetchall())

    def _create_schema(self) -> None:
        assert self._conn is not None
        self._conn.executescript(DDL)

    def _insert_meta(self, *, world_id: str, save_name: str) -> None:
        from tavern import __version__
        with self._tx() as conn:
            conn.execute(
                "INSERT INTO save_meta "
                "(id, schema_version, world_id, save_name, created_at, tavern_version) "
                "VALUES (1, ?, ?, ?, ?, ?)",
                (SCHEMA_VERSION, world_id, save_name, _now_iso(), __version__),
            )

    def _insert_state(self) -> None:
        with self._tx() as conn:
            conn.execute(
                "INSERT INTO world_state (id, updated_at) VALUES (1, ?)",
                (_now_iso(),),
            )

    def _check_schema(self) -> None:
        row = self._one("SELECT schema_version FROM save_meta WHERE id = 1")
        if row is None:
            raise SaveError(f"save file {self._path} is missing save_meta")
        v = row["schema_version"]
        if v != SCHEMA_VERSION:
            raise SchemaMismatchError(
                f"save was created by tavern schema v{v}, "
                f"current is v{SCHEMA_VERSION}. "
                f"See docs/CHANGELOG.md for upgrade notes."
            )


# ── module-level helpers ─────────────────────────────────────────────────


def list_saves() -> list[SaveSummary]:
    """Enumerate saves in stable name order. Broken files are silently skipped."""
    d = saves_dir()
    if not d.is_dir():
        return []
    out: list[SaveSummary] = []
    for p in sorted(d.glob("*.db")):
        name = p.stem
        try:
            with sqlite3.connect(str(p)) as conn:
                conn.row_factory = sqlite3.Row
                meta = conn.execute(
                    "SELECT world_id FROM save_meta WHERE id = 1"
                ).fetchone()
                state = conn.execute(
                    "SELECT turn_count, updated_at FROM world_state WHERE id = 1"
                ).fetchone()
        except sqlite3.Error:
            continue
        if meta is None or state is None:
            continue
        out.append(
            SaveSummary(
                name=name,
                path=p,
                world_id=meta["world_id"],
                turn_count=state["turn_count"],
                updated_at=state["updated_at"],
            )
        )
    return out


def delete_save(name: str) -> None:
    """Delete a save (and its WAL / SHM sidecar files)."""
    p = save_path(name)
    if not p.exists():
        raise SaveNotFoundError(f"save '{name}' not found at {p}")
    for candidate in (p, p.with_suffix(".db-wal"), p.with_suffix(".db-shm")):
        if candidate.exists():
            candidate.unlink()
