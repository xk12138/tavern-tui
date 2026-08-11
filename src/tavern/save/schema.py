"""Schema constants and SQL DDL for the save-file database.

Schema is intentionally frozen at v1 for this release. Future versions will
add a migration path in `store.py` — we deliberately do NOT execute
migrations here, so bumping SCHEMA_VERSION on old files fails loudly.
"""

from __future__ import annotations

# Bump whenever the DDL below changes in a way that isn't a purely additive
# ALTER TABLE that new code tolerates on old data. See PRD §5.4.
SCHEMA_VERSION = 2


DDL = """
CREATE TABLE IF NOT EXISTS save_meta (
    id             INTEGER PRIMARY KEY CHECK (id = 1),
    schema_version INTEGER NOT NULL,
    world_id       TEXT NOT NULL,
    save_name      TEXT NOT NULL,
    created_at     TEXT NOT NULL,
    tavern_version TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS world_state (
    id             INTEGER PRIMARY KEY CHECK (id = 1),
    turn_count     INTEGER NOT NULL DEFAULT 0,
    current_scene  TEXT NOT NULL DEFAULT '',
    day            INTEGER NOT NULL DEFAULT 1,
    time_of_day    TEXT NOT NULL DEFAULT '',
    updated_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scene_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    turn_no    INTEGER NOT NULL,
    role       TEXT NOT NULL CHECK (role IN ('player','gm','system')),
    text       TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_scene_log_turn ON scene_log(turn_no);

CREATE TABLE IF NOT EXISTS scene_summary (
    id                  INTEGER PRIMARY KEY CHECK (id = 1),
    summary_text        TEXT NOT NULL,
    covered_up_to_turn  INTEGER NOT NULL,
    generated_at        TEXT NOT NULL
);
"""


# The set of roles accepted for scene_log.role — kept in sync with the CHECK
# constraint above so Python-side validation returns a nicer error than the
# raw sqlite3 IntegrityError.
VALID_ROLES = frozenset({"player", "gm", "system"})
