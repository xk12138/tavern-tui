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

__version__ = "0.8.0"

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
