"""Save store: lifecycle, writes, reads, rewind, copy, schema check."""

from __future__ import annotations

import sqlite3

import pytest

from tavern.save import (
    Save,
    SaveError,
    SaveExistsError,
    SaveNotFoundError,
    SchemaMismatchError,
    delete_save,
    list_saves,
    save_path,
)


# ── lifecycle ────────────────────────────────────────────────────────────


def test_new_creates_file(tavern_home):
    s = Save.new("run-1", world_id="minimal")
    try:
        assert save_path("run-1").is_file()
        assert s.world_id == "minimal"
        assert s.name == "run-1"
        assert s.state.turn_count == 0
    finally:
        s.close()


def test_new_refuses_existing(tavern_home):
    s = Save.new("run-1", world_id="minimal")
    s.close()
    with pytest.raises(SaveExistsError):
        Save.new("run-1", world_id="minimal")


def test_open_nonexistent(tavern_home):
    with pytest.raises(SaveNotFoundError):
        Save.open("ghost")


def test_close_is_idempotent(tavern_home):
    s = Save.new("run-1", world_id="x")
    s.close()
    s.close()   # should not raise


def test_context_manager(tavern_home):
    with Save.new("run-1", world_id="x") as s:
        assert s.state.turn_count == 0


# ── turns ────────────────────────────────────────────────────────────────


def test_append_and_read_turns(tavern_home):
    with Save.new("r", world_id="w") as s:
        s.append_turn("system", "opening", turn_no=0)
        s.append_turn("player", "look", turn_no=1)
        s.append_turn("gm", "you see a wall", turn_no=1)
        s.update_state(turn_count=1)

        turns = s.turns()
        assert len(turns) == 3
        assert [t.role for t in turns] == ["system", "player", "gm"]
        assert turns[1].text == "look"


def test_recent_turns_returns_last_n(tavern_home):
    with Save.new("r", world_id="w") as s:
        for i in range(1, 6):
            s.append_turn("player", f"p{i}", turn_no=i)
            s.append_turn("gm", f"g{i}", turn_no=i)
        s.update_state(turn_count=5)

        r = s.recent_turns(4)
        assert len(r) == 4
        # order preserved chronologically
        assert r[0].text == "p4"
        assert r[-1].text == "g5"


def test_invalid_role_rejected(tavern_home):
    with Save.new("r", world_id="w") as s:
        with pytest.raises(SaveError):
            s.append_turn("director", "note", turn_no=1)


# ── state updates ────────────────────────────────────────────────────────


def test_update_state_partial(tavern_home):
    with Save.new("r", world_id="w") as s:
        s.update_state(turn_count=3, current_scene="tavern")
        st = s.state
        assert st.turn_count == 3
        assert st.current_scene == "tavern"
        assert st.day == 1                  # unchanged
        assert st.time_of_day == ""

        s.update_state(day=2, time_of_day="dusk")
        st = s.state
        assert st.turn_count == 3           # still there
        assert st.day == 2


def test_update_state_noop(tavern_home):
    with Save.new("r", world_id="w") as s:
        s.update_state()   # nothing to update — should not crash
        assert s.state.turn_count == 0


# ── rewind ───────────────────────────────────────────────────────────────


def test_rewind_removes_last_pairs(tavern_home):
    with Save.new("r", world_id="w") as s:
        for i in range(1, 4):
            s.append_turn("player", f"p{i}", turn_no=i)
            s.append_turn("gm", f"g{i}", turn_no=i)
        s.update_state(turn_count=3)

        deleted = s.rewind(1)
        assert deleted == 2
        assert s.state.turn_count == 2
        assert all(t.turn_no <= 2 for t in s.turns())


def test_rewind_multiple(tavern_home):
    with Save.new("r", world_id="w") as s:
        for i in range(1, 6):
            s.append_turn("player", f"p{i}", turn_no=i)
            s.append_turn("gm", f"g{i}", turn_no=i)
        s.update_state(turn_count=5)

        deleted = s.rewind(3)
        assert deleted == 6
        assert s.state.turn_count == 2


def test_rewind_beyond_start_is_safe(tavern_home):
    with Save.new("r", world_id="w") as s:
        s.append_turn("player", "hi", turn_no=1)
        s.append_turn("gm", "hi", turn_no=1)
        s.update_state(turn_count=1)

        deleted = s.rewind(99)
        assert deleted == 2
        assert s.state.turn_count == 0


def test_rewind_when_empty(tavern_home):
    with Save.new("r", world_id="w") as s:
        assert s.rewind(1) == 0


def test_rewind_zero_or_negative(tavern_home):
    with Save.new("r", world_id="w") as s:
        s.append_turn("player", "hi", turn_no=1)
        s.append_turn("gm", "hi", turn_no=1)
        s.update_state(turn_count=1)

        assert s.rewind(0) == 0
        assert s.rewind(-3) == 0
        assert s.state.turn_count == 1


# ── copy ─────────────────────────────────────────────────────────────────


def test_copy_to_creates_independent_file(tavern_home):
    src = Save.new("src", world_id="w")
    try:
        src.append_turn("player", "p1", turn_no=1)
        src.append_turn("gm", "g1", turn_no=1)
        src.update_state(turn_count=1)

        dst = src.copy_to("dst")
        try:
            assert save_path("dst").is_file()
            assert dst.name == "dst"
            assert dst.state.turn_count == 1

            # mutate dst, src should be untouched
            dst.append_turn("player", "p2", turn_no=2)
            dst.append_turn("gm", "g2", turn_no=2)
            dst.update_state(turn_count=2)
            assert dst.state.turn_count == 2

            # reopen src fresh (avoid cached state on the original obj)
            src.close()
            src2 = Save.open("src")
            try:
                assert src2.state.turn_count == 1
            finally:
                src2.close()
        finally:
            dst.close()
    finally:
        if src._conn is not None:  # type: ignore[attr-defined]
            src.close()


def test_copy_to_refuses_existing(tavern_home):
    a = Save.new("a", world_id="w"); a.close()
    b = Save.new("b", world_id="w")
    try:
        with pytest.raises(SaveExistsError):
            b.copy_to("a")
    finally:
        b.close()


# ── schema check ─────────────────────────────────────────────────────────


def test_schema_mismatch_detected(tavern_home):
    s = Save.new("run", world_id="w")
    p = s.path
    s.close()

    # Manually corrupt the schema version
    with sqlite3.connect(str(p)) as conn:
        conn.execute("UPDATE save_meta SET schema_version = 999 WHERE id = 1")

    with pytest.raises(SchemaMismatchError):
        Save.open("run")


# ── list / delete ────────────────────────────────────────────────────────


def test_list_saves_empty(tavern_home):
    assert list_saves() == []


def test_list_saves_sorted(tavern_home):
    for n in ["c", "a", "b"]:
        Save.new(n, world_id="w").close()
    names = [s.name for s in list_saves()]
    assert names == sorted(names)


def test_list_saves_skips_broken_files(tavern_home):
    Save.new("ok", world_id="w").close()
    # drop a bogus .db that isn't a sqlite file
    broken = save_path("broken")
    broken.write_bytes(b"not sqlite")
    names = [s.name for s in list_saves()]
    assert "ok" in names
    assert "broken" not in names


def test_delete_save(tavern_home):
    Save.new("gone", world_id="w").close()
    assert save_path("gone").exists()
    delete_save("gone")
    assert not save_path("gone").exists()


def test_delete_missing_raises(tavern_home):
    with pytest.raises(SaveNotFoundError):
        delete_save("nope")
