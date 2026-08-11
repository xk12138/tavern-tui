"""Where exported novels live.

Kept separate from `tavern.config.tavern_home` because novels are user
artefacts meant to be shared (dropped into iCloud, sent to friends), not
engine state — they don't belong under `.config/tavern`.

Priority for the root directory:
  1. $TAVERN_NOVELS_HOME  (test/container escape hatch)
  2. ~/tavern-novels      (default, per USAGE.md §十)
"""

from __future__ import annotations

import datetime as _dt
import os
import re
from pathlib import Path


def novels_home() -> Path:
    v = os.environ.get("TAVERN_NOVELS_HOME")
    if v:
        return Path(v).expanduser()
    return Path.home() / "tavern-novels"


def default_output_path(save_name: str, *, now: _dt.datetime | None = None) -> Path:
    """`<novels_home>/<save_name>-<YYYYMMDD-HHMMSS>.md`.

    Timestamp is UTC. Slashes / spaces in save_name would already have been
    rejected by the save-name validator, but we defensively sanitise anyway.
    """
    now = now if now is not None else _dt.datetime.now(tz=_dt.timezone.utc)
    stamp = now.strftime("%Y%m%d-%H%M%S")
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", save_name)
    return novels_home() / f"{safe}-{stamp}.md"
