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
    FREE_INPUT_LABEL,
    SuggestionChoice,
    _Line,
    _suggest_loop,
    display_width,
    readline_wide,
    render_choices_block,
    render_choices_plain,
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


# ── suggestion selection: pure logic ──────────────────────────────────────


def _choices() -> list[SuggestionChoice]:
    return [
        SuggestionChoice(label='"say this"', value='"say this"'),
        SuggestionChoice(label="do that", value="do that"),
        SuggestionChoice(label=FREE_INPUT_LABEL, value=None),
    ]


def _drive_keys(chunks: list[bytes], *, use_color: bool = False):
    """Drive `_suggest_loop` with mocked os.read chunks (no pty needed).

    Returns (result, transcript). EOFError → "__EOF__", KeyboardInterrupt
    → "__KBD__".
    """
    import io
    from unittest import mock

    out = io.StringIO()
    reads = iter(chunks + [b""])
    with mock.patch(
        "tavern.repl.lineedit.os.read", side_effect=lambda fd, n: next(reads)
    ):
        try:
            return _suggest_loop(0, out, _choices(), "> ", use_color), out.getvalue()
        except EOFError:
            return "__EOF__", out.getvalue()
        except KeyboardInterrupt:
            return "__KBD__", out.getvalue()


def test_suggest_loop_enter_commits_first_choice():
    result, _ = _drive_keys([b"\r"])
    assert result == '"say this"'


def test_suggest_loop_arrow_down_commits_second():
    result, _ = _drive_keys([b"\x1b[B", b"\r"])
    assert result == "do that"


def test_suggest_loop_up_at_top_stays_first():
    result, _ = _drive_keys([b"\x1b[A", b"\r"])
    assert result == '"say this"'


def test_suggest_loop_typing_jumps_to_free_option_and_stays_green():
    """The core UX: typing must NOT dismiss the list — it highlights the
    free option (green) and the list stays up until Enter."""
    result, transcript = _drive_keys([b"h", b"i", b"\r"], use_color=True)
    assert result == "hi"
    # The free option turned green…
    assert f"\033[32m[3] {FREE_INPUT_LABEL}\033[0m" in transcript
    # …and the list was re-rendered twice (first render + the jump to the
    # free option), i.e. still on screen while typing — not erased.
    assert transcript.count('[1] "say this"') >= 2


def test_suggest_loop_cjk_typing_lands_in_buffer():
    result, _ = _drive_keys(["\u4f60\u597d".encode("utf-8"), b"\r"])
    assert result == "你好"


def test_suggest_loop_backspace_edits_buffer():
    result, _ = _drive_keys([b"h", b"i", b"\x7f", b"\r"])
    assert result == "h"


def test_suggest_loop_free_option_empty_enter_keeps_waiting():
    """Enter on 说点什么 with an empty buffer does nothing; typing then
    submitting works."""
    result, _ = _drive_keys([b"\x1b[B", b"\x1b[B", b"\r", b"x", b"\r"])
    assert result == "x"


def test_suggest_loop_typed_text_wins_over_arrow_selection():
    """Type first, arrow to a suggestion, Enter → the typed text submits."""
    result, _ = _drive_keys([b"h", b"\x1b[A", b"\r"])
    assert result == "h"


def test_suggest_loop_ctrl_c_and_ctrl_d():
    assert _drive_keys([b"\x03"])[0] == "__KBD__"
    assert _drive_keys([b"\x04"])[0] == "__EOF__"


def test_suggest_loop_ctrl_d_with_text_ignored():
    result, _ = _drive_keys([b"h", b"\x04", b"\r"])
    assert result == "h"


# ── virtual-terminal redraw regression ────────────────────────────────────
#
# The suggest-mode redraws emit cursor-up (`ESC [ n A`) and whole-line
# erase (`ESC [ 2 K`) sequences. A plain StringIO transcript can't tell
# whether those land correctly, so we replay them on a tiny virtual screen
# that starts with the opening text ABOVE the block — the setup that
# exposed the "> accumulates and covers the text" bug (an off-by-one in the
# cursor-up count shifted the block up one row per redraw).


def _simulate_screen(transcript: str, initial_lines: list[str], start_row: int) -> list[str]:
    lines = list(initial_lines)
    row, col = start_row, 0
    i = 0
    while i < len(transcript):
        ch = transcript[i]
        if ch == "\x1b":
            if i + 1 < len(transcript) and transcript[i + 1] == "[":
                j = i + 2
                while j < len(transcript) and not ("@" <= transcript[j] <= "~"):
                    j += 1
                if j < len(transcript):
                    params, final = transcript[i + 2 : j], transcript[j]
                    if final == "A":  # cursor up
                        row = max(0, row - int(params or "1"))
                    elif final == "B":  # cursor down
                        row += int(params or "1")
                    elif final == "K":  # erase line (2 = whole line)
                        lines[row] = "" if params == "2" else lines[row][:col]
                    i = j
            else:
                i += 1
            i += 1
            continue
        if ch == "\r":
            col = 0
        elif ch == "\n":
            row += 1
            col = 0
            if row >= len(lines):
                lines.append("")
        else:
            while row >= len(lines):
                lines.append("")
            if col < len(lines[row]):
                lines[row] = lines[row][:col] + ch + lines[row][col + 1 :]
            else:
                lines[row] += ch
            col += 1
        i += 1
    return lines


def test_suggest_redraw_keeps_single_prompt_line_and_preserves_text_above():
    """The reported bug: pressing ↑/↓ stacked "> " prompts and crept the
    list up over the text above. After the fix, repeated redraws leave
    exactly one prompt line and never touch the rows above the block."""
    import io
    from unittest import mock

    out = io.StringIO()
    keys = [b"\x1b[B", b"\x1b[B", b"\x1b[B", b"\x1b[A", b"\x1b[B", b"\x1b[A", b""]
    reads = iter(keys)
    with mock.patch(
        "tavern.repl.lineedit.os.read", side_effect=lambda fd, n: next(reads)
    ):
        try:
            _suggest_loop(0, out, _choices(), "> ", use_color=False)
        except EOFError:
            pass

    above = ["夜色里,那道目光的主人终于动了……", "", "(provider: DeepSeek ...)", ""]
    screen = _simulate_screen(out.getvalue(), above, start_row=3)
    assert screen.count("> ") == 1
    # The list stays exactly where it was first rendered (rows 3–5)…
    assert screen[3].startswith('  [1] "say this"')
    assert screen[4] == "  [2] do that"
    assert screen[5] == f"  [3] {FREE_INPUT_LABEL}"
    # …and the text above the block is untouched.
    assert screen[0].startswith("夜色里")
    assert screen[2].startswith("(provider:")


def test_suggest_commit_clears_block_and_prompts_in_place():
    import io
    from unittest import mock

    out = io.StringIO()
    keys = [b"\x1b[B", b"\r", b""]  # ↓ to [2], Enter commits it
    reads = iter(keys)
    with mock.patch(
        "tavern.repl.lineedit.os.read", side_effect=lambda fd, n: next(reads)
    ):
        result = _suggest_loop(0, out, _choices(), "> ", use_color=False)

    assert result == "do that"
    above = ["夜色里,那道目光的主人终于动了……", "", "(provider: DeepSeek ...)", ""]
    screen = _simulate_screen(out.getvalue(), above, start_row=3)
    # The block is gone; the committed line sits at the block's top row and
    # no stale prompt remains anywhere below.
    assert screen[3] == "> do that"
    assert screen.count("> ") == 0  # "> do that" isn't a bare "> "


def test_render_choices_block_highlights_selected_green_free_gray():
    c = _choices()
    block = render_choices_block(c, selected=0, prompt="> ", use_color=True)
    assert "\033[32m[1] \"say this\"\033[0m" in block
    assert "[2] do that" in block
    assert f"\033[90m[3] {FREE_INPUT_LABEL}\033[0m" in block
    assert block.endswith("> ")


def test_render_choices_block_includes_typed_buffer():
    c = _choices()
    block = render_choices_block(c, selected=2, prompt="> ", use_color=True, buffer="hello")
    assert block.endswith("> hello")
    assert f"\033[32m[3] {FREE_INPUT_LABEL}\033[0m" in block


def test_render_choices_block_no_color():
    c = _choices()
    block = render_choices_block(c, selected=0, prompt="> ", use_color=False)
    # No color codes — and the left edge is fixed-width so the rows align.
    assert "\033[32m" not in block
    assert "\033[90m" not in block
    assert "[1] \"say this\"" in block


def test_render_choices_block_rows_aligned():
    """Every row starts at column 2 with a `[N] ` marker, so every label
    starts at column 6 — alignment regression guard for the "选项前面没
    对齐" complaint."""
    c = _choices()
    block = render_choices_block(c, selected=0, prompt="> ", use_color=False)
    for row in block.split("\n")[:-1]:
        assert row[2] == "["
        assert row[5] == " "  # marker is exactly "[N] " → label at col 6


def test_render_choices_plain_numbered():
    c = _choices()
    plain = render_choices_plain(c)
    assert plain == '  [1] "say this"\n  [2] do that\n  [3] 说点什么…\n'


# ── end-to-end (pty) ─────────────────────────────────────────────────────


# On non-POSIX (or when pty isn't usable), skip the end-to-end tests. The
# unit tests above already cover the width math that fixes the bug.
pytestmark_pty = pytest.mark.skipif(
    sys.platform == "win32", reason="pty is POSIX-only"
)


def _drive(
    inputs: bytes,
    *,
    prompt: str = "> ",
    choices: list[SuggestionChoice] | None = None,
) -> tuple[str, str]:
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
                line = readline_wide(
                    prompt, stdin=real_stdin, stdout=real_stdout, choices=choices
                )
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


# ── end-to-end: suggestion selection (pty) ────────────────────────────────


@pytestmark_pty
def test_pty_suggest_enter_commits_first_choice():
    c = _choices()
    line, _ = _drive(b"\r", choices=c)
    assert line == "say this"


@pytestmark_pty
def test_pty_suggest_arrow_down_commits_second():
    c = _choices()
    line, _ = _drive(b"\x1b[B\r", choices=c)
    assert line == "do that"


@pytestmark_pty
def test_pty_suggest_up_at_top_stays_first():
    c = _choices()
    line, _ = _drive(b"\x1b[A\r", choices=c)
    assert line == "say this"


@pytestmark_pty
def test_pty_suggest_typing_commits_on_enter():
    """Typing highlights the free option; the list stays until Enter submits."""
    c = _choices()
    line, _ = _drive(b"hello\r", choices=c)
    assert line == "hello"


@pytestmark_pty
def test_pty_suggest_free_option_then_type():
    """Down twice to 说点什么, Enter, then type freely."""
    c = _choices()
    line, _ = _drive(b"\x1b[B\x1b[B\rhi\r", choices=c)
    assert line == "hi"


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
