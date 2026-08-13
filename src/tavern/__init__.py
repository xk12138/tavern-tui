"""Tavern — a CLI-native, LLM-driven interactive narrative engine.

Public API surface for the worldpack subsystem is exposed here so callers can:

    from tavern import (
        load_worldpack, validate_worldpack,
        install, list_installed, uninstall,
    )
"""

from tavern.worldpack.install import (
    InstallError,
    InstalledWorld,
    install,
    list_installed,
    uninstall,
)
from tavern.worldpack.loader import load_worldpack
from tavern.worldpack.validator import validate_worldpack

# Version is written by hatch-vcs at build time into _version.py. In a fresh
# source checkout (never built, never installed) that file doesn't exist yet —
# fall back to a sentinel so `import tavern` still works during dev.
try:
    from tavern._version import __version__  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - only hit in un-built source checkouts
    __version__ = "0.0.0+unknown"

__all__ = [
    "load_worldpack",
    "validate_worldpack",
    "install",
    "list_installed",
    "uninstall",
    "InstalledWorld",
    "InstallError",
    "__version__",
]
