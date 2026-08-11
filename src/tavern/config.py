"""Filesystem layout for user-owned Tavern state.

`~/.config/tavern/` is the default. Two escape hatches:
  * TAVERN_CONFIG_HOME=/path/to/dir  — takes precedence over anything else
  * XDG_CONFIG_HOME=/path            — respected on Linux/macOS if set

The first is Tavern-specific and always wins; it exists so tests, containers,
and users with unusual setups can force an isolated home without touching
their real config.
"""

from __future__ import annotations

import os
from pathlib import Path


def tavern_home() -> Path:
    """Return the Tavern config root (creates nothing).

    Priority:
      1. $TAVERN_CONFIG_HOME
      2. $XDG_CONFIG_HOME/tavern
      3. ~/.config/tavern
    """
    if v := os.environ.get("TAVERN_CONFIG_HOME"):
        return Path(v).expanduser()
    if v := os.environ.get("XDG_CONFIG_HOME"):
        return Path(v).expanduser() / "tavern"
    return Path.home() / ".config" / "tavern"


def worlds_dir() -> Path:
    """Where installed world packs live: `<tavern_home>/worlds/`."""
    return tavern_home() / "worlds"


def ensure_dirs() -> None:
    """Create the config root and worlds directory if they don't exist."""
    worlds_dir().mkdir(parents=True, exist_ok=True)
