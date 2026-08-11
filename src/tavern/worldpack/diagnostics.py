"""Diagnostic types + human-readable rendering.

Kept separate from the validator so callers that want machine-readable output
(e.g. a future `--json` flag) can consume `ValidationReport` directly.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import Literal

from tavern.worldpack.schema import WorldPack

Level = Literal["error", "warning", "info"]


@dataclass
class Diagnostic:
    level: Level
    code: str            # E001 / W004 / I001
    message: str
    location: str | None = None
    hint: str | None = None


@dataclass
class ValidationReport:
    ok: bool
    diagnostics: list[Diagnostic] = field(default_factory=list)
    pack: WorldPack | None = None

    @property
    def errors(self) -> list[Diagnostic]:
        return [d for d in self.diagnostics if d.level == "error"]

    @property
    def warnings(self) -> list[Diagnostic]:
        return [d for d in self.diagnostics if d.level == "warning"]

    @property
    def infos(self) -> list[Diagnostic]:
        return [d for d in self.diagnostics if d.level == "info"]


# ── rendering ─────────────────────────────────────────────────────────────

_RESET = "\033[0m"
_RED = "\033[31m"
_YELLOW = "\033[33m"
_BLUE = "\033[34m"
_DIM = "\033[2m"
_BOLD = "\033[1m"


def _use_color(stream) -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    return hasattr(stream, "isatty") and stream.isatty()


def _paint(text: str, color: str, enabled: bool) -> str:
    return f"{color}{text}{_RESET}" if enabled else text


_LEVEL_MARK = {"error": ("✗", _RED), "warning": ("⚠", _YELLOW), "info": ("ℹ", _BLUE)}


def render_report(
    report: ValidationReport,
    *,
    verbose: bool = False,
    stream=None,
) -> None:
    """Write a human-readable report to stream (default stdout)."""
    stream = stream if stream is not None else sys.stdout
    color = _use_color(stream)

    diagnostics = report.diagnostics if verbose else [
        d for d in report.diagnostics if d.level != "info"
    ]

    grouped: dict[str, list[Diagnostic]] = {}
    for d in diagnostics:
        key = d.location or "(worldpack)"
        # strip line number for grouping so all issues in same file cluster
        group_key = key.split(":", 1)[0]
        grouped.setdefault(group_key, []).append(d)

    for group, items in grouped.items():
        stream.write(_paint(group, _BOLD, color) + "\n")
        for d in items:
            mark, mark_color = _LEVEL_MARK[d.level]
            stream.write(f"  {_paint(mark, mark_color, color)} {d.code}  {d.message}\n")
            if d.location and ":" in d.location:
                line = d.location.split(":", 1)[1]
                stream.write(f"      {_paint(f'at line {line}', _DIM, color)}\n")
            if d.hint:
                stream.write(f"      {_paint('→ ' + d.hint, _DIM, color)}\n")
        stream.write("\n")

    _render_summary(report, stream, color)


def _render_summary(
    report: ValidationReport, stream, color: bool
) -> None:
    stream.write(_paint("── Summary ──", _DIM, color) + "\n")

    e_count = len(report.errors)
    w_count = len(report.warnings)

    parts = [
        _paint(f"{e_count} error{'s' if e_count != 1 else ''}", _RED if e_count else "", color and bool(e_count)),
        _paint(f"{w_count} warning{'s' if w_count != 1 else ''}", _YELLOW if w_count else "", color and bool(w_count)),
    ]

    if report.pack:
        parts.append(f"{len(report.pack.npcs)} npc{'s' if len(report.pack.npcs) != 1 else ''}")
        parts.append(f"{len(report.pack.locations)} location{'s' if len(report.pack.locations) != 1 else ''}")
        parts.append(f"{len(report.pack.templates)} template{'s' if len(report.pack.templates) != 1 else ''}")
        parts.append(f"~{report.pack.estimated_tokens} tokens")

    stream.write(" · ".join(parts) + "\n")

    if report.ok:
        msg = "Validation passed."
        stream.write(_paint(msg, "\033[32m", color) + "\n")
    else:
        stream.write(_paint("Validation failed.", _RED, color) + "\n")
