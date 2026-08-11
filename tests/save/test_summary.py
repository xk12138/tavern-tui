"""scene_summary table: read/write/UPSERT + rewind isolation."""

from __future__ import annotations

from tavern.save import Save


def test_summary_absent_by_default(tavern_home):
    s = Save.new("s1", world_id="minimal")
    try:
        assert s.summary() is None
    finally:
        s.close()


def test_set_summary_persists(tavern_home):
    s = Save.new("s1", world_id="minimal")
    try:
        s.set_summary("A tavern. A patron. A knife.", covered_up_to_turn=10)
        got = s.summary()
        assert got is not None
        assert got.summary_text == "A tavern. A patron. A knife."
        assert got.covered_up_to_turn == 10
        assert got.generated_at  # ISO timestamp, non-empty
    finally:
        s.close()


def test_set_summary_overwrites_singleton(tavern_home):
    s = Save.new("s1", world_id="minimal")
    try:
        s.set_summary("v1", covered_up_to_turn=10)
        s.set_summary("v2 replaces v1", covered_up_to_turn=20)
        got = s.summary()
        assert got is not None
        assert got.summary_text == "v2 replaces v1"
        assert got.covered_up_to_turn == 20
    finally:
        s.close()


def test_rewind_leaves_summary_alone(tavern_home):
    s = Save.new("s1", world_id="minimal")
    try:
        s.append_turn("player", "hi", turn_no=1)
        s.append_turn("gm", "hello", turn_no=1)
        s.append_turn("player", "again", turn_no=2)
        s.append_turn("gm", "again reply", turn_no=2)
        s.update_state(turn_count=2)
        s.set_summary("a summary", covered_up_to_turn=1)
        s.rewind(1)  # drop turn 2
        # summary is orthogonal — the covered_up_to_turn is just data, not
        # something rewind touches. Confirms the singleton lives in its own
        # table and DELETE FROM scene_log doesn't reach it.
        got = s.summary()
        assert got is not None
        assert got.covered_up_to_turn == 1
        assert got.summary_text == "a summary"
    finally:
        s.close()


def test_turns_after_filters_by_turn_no(tavern_home):
    s = Save.new("s1", world_id="minimal")
    try:
        s.append_turn("system", "hook", turn_no=0)
        for i in range(1, 6):
            s.append_turn("player", f"p{i}", turn_no=i)
            s.append_turn("gm", f"g{i}", turn_no=i)
        after_3 = s.turns_after(3)
        # Turns 4 and 5 remain (4 rows total).
        assert [t.turn_no for t in after_3] == [4, 4, 5, 5]
        assert [t.role for t in after_3] == ["player", "gm", "player", "gm"]
    finally:
        s.close()
