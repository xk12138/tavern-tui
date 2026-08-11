"""Shared pytest fixtures.

`FIXTURES_DIR` points at the on-disk fixture worlds we use for validator tests.
`tavern_home` redirects TAVERN_CONFIG_HOME to a per-test tmpdir so tests can
run install/list/uninstall without touching the user's real ~/.config/tavern.
"""

from pathlib import Path
import sys

import pytest

# Make `src/` importable without installing the package (matches pyproject config).
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

_FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def FIXTURES_DIR() -> Path:
    """Absolute path to the tests/fixtures/ directory."""
    return _FIXTURES


@pytest.fixture
def tavern_home(monkeypatch, tmp_path: Path) -> Path:
    """Isolate TAVERN_CONFIG_HOME to a per-test tmpdir.

    Also clears XDG_CONFIG_HOME so it doesn't leak in from the developer
    environment.
    """
    home = tmp_path / "tavern-home"
    monkeypatch.setenv("TAVERN_CONFIG_HOME", str(home))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    return home
