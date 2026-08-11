"""Save name validation + path resolution."""

from __future__ import annotations

import pytest

from tavern.save import SaveNameError, save_path, saves_dir


def test_saves_dir_under_tavern_home(tavern_home):
    assert saves_dir() == tavern_home / "saves"


def test_valid_names(tavern_home):
    # each of these should resolve to a path without raising
    for n in ["a", "run1", "my_run", "my.run", "my-run", "A"*64]:
        p = save_path(n)
        assert p.suffix == ".db"


def test_invalid_names(tavern_home):
    bad = [
        "",                    # empty
        ".hidden",             # leading dot
        "-leading",            # leading dash
        "with/slash",          # path traversal
        "with\\backslash",
        "with space",
        "with:colon",
        "a" * 65,              # too long
        "有中文",               # unicode not allowed for now
    ]
    for n in bad:
        with pytest.raises(SaveNameError):
            save_path(n)


def test_name_type_check(tavern_home):
    with pytest.raises(SaveNameError):
        save_path(None)   # type: ignore[arg-type]
