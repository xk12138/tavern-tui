"""Tests for the CJK-safe line editor.

Two layers:
  1. Pure-function width math + `_Line` accounting (no I/O, easy).
  2. End-to-end read through a pseudo-terminal — this is the real
     regression, since the bug only surfaces when the editor has to
     emit the *right number of erase columns* for a wide glyph.
"""

from __future__ import annotations

import io
import os
import pty
import re
import select
import sys

import pytest

from tavern.repl.lineedit import (
    _Line,
    display_width,
    readline_wide,
    string_width,
)


# ── width math ───────────────────────────────────────────────────────────


def test_display_width_ascii():
    assert display_width("a") == 1
    assert display_width(" ") == 1
    assert display_width("~") == 1


def test_display_width_cjk_wide():
    # Chinese ideographs — Unicode East Asian Width = W.
    assert display_width("你") == 2
    assert display_width("好") == 2
    assert display_width("酒") == 2


def test_display_width_fullwidth_punctuation():
    # Fullwidth comma / quote — East Asian Width = F. These are the sneakiest
    # regressions: they look narrow at a glance but occupy 2 columns.
    assert display_width("，") == 2
    assert display_width("。") == 2


def test_display_width_combining_mark_is_zero():
    # U+0301 COMBINING ACUTE ACCENT — attaches to the previous base char.
    assert display_width("́") == 0


def test_display_width_control_char_is_zero():
    # Would otherwise poison the accounting if it slipped into the buffer.
    assert display_width("\x1b") == 0
    assert display_width("\x00") == 0


def test_display_width_empty():
    assert display_width("") == 0


def test_string_width_mixed():
    # 4 ASCII columns (hi, ) + 5 wide chars × 2 columns = 14
    assert string_width("hi, 老板来杯酒") == 4 + 2 * 5


# ── _Line accounting ─────────────────────────────────────────────────────


def test_line_append_and_backspace_ascii():
    line = _Line()
    assert line.append("h") == 1
    assert line.append("i") == 1
    assert line.text == "hi"
    assert line.width == 2
    assert line.backspace() == 1
    assert line.text == "h"
    assert line.width == 1


def test_line_backspace_wide_char_returns_two():
    """The core bug: erasing 你 must report 2 columns, not 1."""
    line = _Line()
    line.append("你")
    assert line.width == 2
    assert line.backspace() == 2
    assert line.text == ""
    assert line.width == 0


def test_line_backspace_mixed_run():
    line = _Line()
    for ch in "老板,来一壶酒":
        line.append(ch)
    # 老板 = 4, ',' = 1, 来一壶酒 = 8 → total 13
    assert line.width == 13
    # Remove 酒 (wide)
    assert line.backspace() == 2
    # Remove 壶 (wide)
    assert line.backspace() == 2
    # Remove 一 (wide)
    assert line.backspace() == 2
    # Remove 来 (wide)
    assert line.backspace() == 2
    # Remove ',' (narrow)
    assert line.backspace() == 1
    assert line.text == "老板"
    assert line.width == 4


def test_line_backspace_on_empty_returns_zero():
    line = _Line()
    assert line.backspace() == 0
    assert line.text == ""


def test_line_backspace_absorbs_combining_marks():
    """é (e + U+0301) must erase in a single backspace, freeing 1 column."""
    line = _Line()
    line.append("e")
    line.append("́")  # combining acute
    assert line.width == 1  # visually one glyph
    assert line.backspace() == 1
    assert line.text == ""


# ── end-to-end (pty) ─────────────────────────────────────────────────────


# On non-POSIX (or when pty isn't usable), skip the end-to-end tests. The
# unit tests above already cover the width math that fixes the bug.
pytestmark_pty = pytest.mark.skipif(
    sys.platform == "win32", reason="pty is POSIX-only"
)


def _drive(inputs: bytes, *, prompt: str = "> ") -> tuple[str, str]:
    """Fork a child that runs readline_wide on a pty; feed it `inputs`.

    A non-empty `prompt` doubles as a race-free sync sentinel: the parent
    won't push input until it has seen the prompt echo back, which
    guarantees the child has already entered raw mode.
    """
    pid, fd = pty.fork()
    if pid == 0:
        # Child — pytest replaced sys.stdin/stdout with capture shims before
        # the fork; put them back to the real pty fds so the editor sees a TTY.
        try:
            real_stdin = os.fdopen(0, "rb", buffering=0)
            real_stdout = os.fdopen(1, "wb", buffering=0)
            try:
                line = readline_wide(prompt, stdin=real_stdin, stdout=real_stdout)
            except EOFError:
                os.write(1, b"__EOF__")
                os._exit(0)
            except KeyboardInterrupt:
                os.write(1, b"__KBD__")
                os._exit(0)
            payload = line.encode("utf-8")
            os.write(1, b"\n<<<" + payload + b">>>")
        except BaseException as exc:  # pragma: no cover — surface crashes to parent
            os.write(1, f"__CHILD_ERROR__ {exc!r}".encode("utf-8"))
        os._exit(0)

    # Parent — first wait for the prompt to appear so the child is in raw
    # mode before we push the input. Without this, cooked-mode line
    # discipline can process the input and the test never exercises our
    # editor.
    if prompt:
        _wait_for_bytes(fd, prompt.encode("utf-8"), timeout=2.0)

    os.write(fd, inputs)

    chunks: list[bytes] = []
    if prompt:
        # Prepend what we already consumed while waiting for the prompt so
        # the transcript is complete.
        chunks.append(prompt.encode("utf-8"))
    try:
        while True:
            r, _, _ = select.select([fd], [], [], 2.0)
            if not r:
                break
            try:
                data = os.read(fd, 4096)
            except OSError:
                break
            if not data:
                break
            chunks.append(data)
    finally:
        os.close(fd)
        os.waitpid(pid, 0)

    transcript = b"".join(chunks).decode("utf-8", errors="replace")
    match = re.search(r"<<<(.*)>>>", transcript, re.DOTALL)
    line = match.group(1) if match else ""
    return line, transcript


def _wait_for_bytes(fd: int, needle: bytes, *, timeout: float) -> None:
    """Consume bytes from `fd` until `needle` has been seen; discard them."""
    seen = bytearray()
    while True:
        r, _, _ = select.select([fd], [], [], timeout)
        if not r:
            return
        try:
            data = os.read(fd, 128)
        except OSError:
            return
        if not data:
            return
        seen.extend(data)
        if needle in seen:
            return


@pytestmark_pty
def test_pty_backspace_wide_char_erases_two_columns():
    """The regression: typing 你 then backspace must overwrite 2 columns.

    We look for the erase pattern in the transcript: b"\\b  \\b\\b" — two
    backspaces, two spaces, two backspaces. Under the buggy libedit
    behavior this would be `\\b \\b` (one column), leaving half of 你 on
    screen.
    """
    line, transcript = _drive("你\x7f\r".encode("utf-8"))
    assert line == ""
    assert "\b\b  \b\b" in transcript, (
        f"expected 2-column erase sequence in transcript, got: {transcript!r}"
    )


@pytestmark_pty
def test_pty_backspace_ascii_erases_one_column():
    line, transcript = _drive(b"a\x7f\r")
    assert line == ""
    # Exactly one column of erase — not two, not zero.
    assert "\b \b" in transcript


@pytestmark_pty
def test_pty_typing_and_committing_mixed_string():
    line, _ = _drive("老板,来一壶酒\r".encode("utf-8"))
    assert line == "老板,来一壶酒"


@pytestmark_pty
def test_pty_backspace_then_retype():
    """Simulate: type "你好", backspace once, type "吗", commit → "你吗"."""
    keys = "你好".encode("utf-8") + b"\x7f" + "吗".encode("utf-8") + b"\r"
    line, transcript = _drive(keys)
    assert line == "你吗"
    # The backspace of 好 must emit a 2-column erase.
    assert "\b\b  \b\b" in transcript


@pytestmark_pty
def test_pty_arrow_keys_are_swallowed():
    """Left/Right/Up arrows must not leak escape bytes into the buffer."""
    # Up arrow = ESC [ A. We type it in the middle of "ab" and then commit.
    line, _ = _drive(b"a\x1b[Ab\r")
    assert line == "ab"


@pytestmark_pty
def test_pty_ctrl_c_raises_keyboard_interrupt():
    line, transcript = _drive(b"abc\x03")
    assert line == ""
    assert "__KBD__" in transcript


@pytestmark_pty
def test_pty_ctrl_d_on_empty_line_raises_eof():
    line, transcript = _drive(b"\x04")
    assert line == ""
    assert "__EOF__" in transcript


@pytestmark_pty
def test_pty_prompt_is_written():
    _, transcript = _drive(b"\r", prompt="tavern> ")
    assert "tavern> " in transcript


# ── fallback path (no TTY) ───────────────────────────────────────────────


def test_readline_wide_falls_back_to_input_when_no_tty(monkeypatch):
    """When stdin isn't a TTY (piped input, CI, tests), use input()."""
    called = {}

    def fake_input(prompt=""):
        called["prompt"] = prompt
        return "piped-line"

    monkeypatch.setattr("builtins.input", fake_input)
    # Force the "not a tty" branch by passing StringIO — it has no fileno.
    result = readline_wide(
        "prompt> ",
        stdin=io.StringIO("piped-line\n"),
        stdout=io.StringIO(),
    )
    assert result == "piped-line"
    assert called["prompt"] == "prompt> "
