"""CJK-safe line editor + interactive suggestion selection for the play REPL.

The default `input()` on macOS goes through libedit, which computes cursor
motion in *characters* rather than *display columns*. Wide glyphs (CJK, most
emoji, fullwidth punctuation) occupy 2 columns in the terminal, so hitting
backspace after typing 你好 erases one column of cells but the cursor only
walks back one character — leaving half of 好 as a "ghost" that the redraw
never covers.

We fix this by reading raw bytes off the tty ourselves, decoding UTF-8 one
codepoint at a time, and doing the width math with
`unicodedata.east_asian_width` (the same rule wcwidth-family libraries
follow). In environments where we can't put the tty into raw mode (non-TTY
stdin/stdout, no `termios`, Windows) we transparently fall back to the
built-in `input()`, so tests and piped input keep working.

Suggestion mode (Claude Code style): when `readline_wide` is called with
`choices`, the editor first renders a numbered list and enters an arrow-key
selection loop:

  [1] "Barkeep, what's the note about?"    ← green = current selection
  [2] Study the watcher at the far table
  [3] 说点什么…                             ← gray = type it yourself

  - ↑/↓ move the selection (green highlight); Enter commits the current option
  - typing does NOT dismiss the list: the first printable character jumps
    the selection to the trailing "type it yourself" option (it turns
    green) and the keystrokes land in the prompt line; the list stays until
    Enter is pressed
  - Enter submits what you typed if you typed anything; otherwise it
    commits the highlighted option (the free option with an empty buffer
    just keeps waiting)
  - Backspace edits the prompt line; Ctrl-C / Ctrl-D behave as usual
  - in piped/non-TTY mode there is no selection loop: the list is printed
    plainly and the caller's typed `[N]` / `:N` fallback picks a suggestion

Escape handling: arrow keys (CSI A/B and SS3 A/B) are surfaced to the
caller as tokens so suggest mode can act on them; in normal line mode they
are swallowed — no escape bytes ever reach the edit buffer.
"""

from __future__ import annotations

import os
import sys
import unicodedata
from dataclasses import dataclass
from typing import IO


# ── suggestion selection UI ──────────────────────────────────────────────


@dataclass
class SuggestionChoice:
    """One selectable row in the suggestion list.

    `value` is the raw line to submit when committed; `None` marks the
    trailing "type it yourself" option.
    """

    label: str
    value: str | None


FREE_INPUT_LABEL = "说点什么…"

_GREEN = "\033[32m"
_GRAY = "\033[90m"
_RESET = "\033[0m"
# Erase the ENTIRE current line (EL 2). Used with a leading \r on every
# redraw so a shorter replacement can never leave stale fragments behind —
# this is what keeps the list's left edge aligned across selection changes.
_ERASE_LINE = "\033[2K"


def _use_color(stream: IO) -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    try:
        return bool(stream.isatty())
    except (ValueError, AttributeError):
        return False


def _paint(text: str, color: str, enabled: bool) -> str:
    return f"{color}{text}{_RESET}" if enabled else text


def render_choices_block(
    choices: list[SuggestionChoice],
    selected: int,
    prompt: str,
    use_color: bool,
    buffer: str = "",
) -> str:
    """The interactive block: numbered list + prompt line (TTY mode).

    `buffer` is the text the player has typed into the prompt line so far —
    kept across redraws (the list stays up while typing).
    """
    lines: list[str] = []
    for i, c in enumerate(choices):
        text = f"[{i + 1}] {c.label}"
        if i == selected:
            text = _paint(text, _GREEN, use_color)
        elif c.value is None:
            text = _paint(text, _GRAY, use_color)
        lines.append("  " + text)
    return "\n".join(lines) + "\n" + prompt + buffer


def render_choices_plain(choices: list[SuggestionChoice]) -> str:
    """Plain numbered list for non-TTY mode (piped input, CI)."""
    lines = [f"  [{i + 1}] {c.label}" for i, c in enumerate(choices)]
    return "\n".join(lines) + "\n"


def _is_printable(token: str) -> bool:
    """A single codepoint that isn't a control/format/surrogate char.

    ASCII and CJK alike — typing 你 while the suggestion list is up must
    land in the prompt line, not get swallowed.
    """
    return len(token) == 1 and unicodedata.category(token)[0] != "C"


# ── character width accounting ────────────────────────────────────────────


def display_width(ch: str) -> int:
    """Return the terminal display width of a single character.

    - 0 for combining marks and other zero-width characters (so composed
      sequences like "é" don't over-erase).
    - 2 for East Asian Wide/Fullwidth characters, per Unicode UAX #11.
    - 1 for everything else.
    """
    if not ch:
        return 0
    if unicodedata.combining(ch):
        return 0
    # 'Cc' = control (\x00-\x1f, \x7f); 'Cf' = format. We should never store
    # these in the buffer, but defensively report 0 so a stray one can't wreck
    # the width accounting.
    if unicodedata.category(ch) in ("Cc", "Cf"):
        return 0
    if unicodedata.east_asian_width(ch) in ("W", "F"):
        return 2
    return 1


def string_width(s: str) -> int:
    """Sum of `display_width` across a string."""
    return sum(display_width(c) for c in s)


class _Line:
    """The in-memory line the editor is currently building.

    Pure state machine — no I/O — so we can unit-test the accounting
    without a pty. The editor holds one of these and asks it what to
    do on each keystroke.
    """

    def __init__(self) -> None:
        self._chars: list[str] = []

    @property
    def text(self) -> str:
        return "".join(self._chars)

    @property
    def width(self) -> int:
        return string_width(self.text)

    def append(self, ch: str) -> int:
        """Append `ch`; return the display width consumed."""
        self._chars.append(ch)
        return display_width(ch)

    def backspace(self) -> int:
        """Remove the last character; return the display width to erase.

        Zero-width combining marks are absorbed together with the base
        character they attach to — otherwise pressing backspace once on
        "é" (e + U+0301) would leave the 'e' visually alone but with the
        internal accent still gone, or vice versa.
        """
        if not self._chars:
            return 0
        width = 0
        while self._chars and display_width(self._chars[-1]) == 0:
            self._chars.pop()
        if self._chars:
            width += display_width(self._chars[-1])
            self._chars.pop()
        return width


# ── entry points ──────────────────────────────────────────────────────────


def readline_wide(
    prompt: str = "",
    *,
    choices: list[SuggestionChoice] | None = None,
    stdin: IO | None = None,
    stdout: IO | None = None,
) -> str:
    """Read a line from the user, correctly redrawing wide characters.

    Semantics match `input()`:
      - Returns the line without the trailing newline.
      - Raises `EOFError` on Ctrl-D at an empty line (or on stream EOF).
      - Raises `KeyboardInterrupt` on Ctrl-C.

    With `choices`, enters suggestion-selection mode (see module docstring);
    the returned string is the committed suggestion's raw line, or the line
    the user typed after dismissing the list. Falls back to `input()` (with
    a plain printed list) when the terminal can't do raw mode.
    """
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout

    if not choices:
        return _readline_plain(prompt, stdin, stdout)

    if not _can_raw_mode(stdin, stdout):
        # Piped / non-TTY: show the options plainly; typed `[N]` / `:N`
        # selection (handled by the caller) still works.
        _write(stdout, render_choices_plain(choices))
        return input(prompt)

    import termios  # local — non-POSIX platforms don't blow up on module load
    import tty

    fd = stdin.fileno()
    old_attrs = termios.tcgetattr(fd)
    try:
        # Enter raw mode BEFORE writing anything so the terminal's cooked
        # line discipline never gets a chance to echo an incoming keystroke
        # with the wrong (1-column) backspace behavior.
        tty.setraw(fd, when=termios.TCSANOW)
        return _suggest_loop(fd, stdout, choices, prompt, _use_color(stdout))
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_attrs)
        # Always finish on a fresh line — raw mode ate the CR/LF echo.
        _write(stdout, "\r\n")


def _readline_plain(prompt: str, stdin: IO, stdout: IO) -> str:
    if not _can_raw_mode(stdin, stdout):
        return input(prompt)

    import termios  # local — non-POSIX platforms don't blow up on module load
    import tty

    fd = stdin.fileno()
    old_attrs = termios.tcgetattr(fd)
    try:
        tty.setraw(fd, when=termios.TCSANOW)
        _write(stdout, prompt)
        return _read_loop(fd, stdout)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_attrs)
        _write(stdout, "\r\n")


def _can_raw_mode(stdin: IO, stdout: IO) -> bool:
    """Are we plausibly attached to a real terminal on both ends?"""
    try:
        import termios  # noqa: F401
        import tty  # noqa: F401
    except ImportError:
        return False
    try:
        return bool(stdin.isatty() and stdout.isatty())
    except (ValueError, AttributeError):
        return False


def _write(stream: IO, text: str) -> None:
    """Write `text` to `stream`, robust to text/binary streams."""
    if not text:
        return
    try:
        stream.write(text)
    except TypeError:
        # Binary stream — encode.
        stream.write(text.encode("utf-8"))
    try:
        stream.flush()
    except Exception:  # pragma: no cover — flush on a bare fd is a no-op
        pass


# ── suggest-mode loop ─────────────────────────────────────────────────────


def _suggest_loop(
    fd: int,
    stdout: IO,
    choices: list[SuggestionChoice],
    prompt: str,
    use_color: bool,
) -> str:
    """Arrow-key selection over `choices`; returns the raw line to submit.

    The list stays on screen the whole time. Enter submits what the player
    typed (if anything); with an empty buffer it commits the highlighted
    suggestion. Typing jumps the highlight to the trailing free-input
    option and lands keystrokes in the prompt line.
    """
    selected = 0
    buffer = _Line()
    _write_block(stdout, choices, selected, prompt, buffer.text, use_color)
    decoder = _Utf8Decoder()

    while True:
        try:
            data = os.read(fd, 32)
        except OSError:
            data = b""
        if not data:
            if buffer.text:
                _commit(stdout, choices, prompt, buffer.text)
                return buffer.text
            raise EOFError

        for token in decoder.feed(data):
            if token in ("\r", "\n"):
                if buffer.text:
                    _commit(stdout, choices, prompt, buffer.text)
                    return buffer.text
                value = choices[selected].value
                if value is None:
                    continue  # empty free input — keep waiting
                _commit(stdout, choices, prompt, value)
                return value

            if token == "\x1b[A":  # up
                if selected > 0:
                    selected -= 1
                    _redraw(stdout, choices, selected, prompt, buffer.text, use_color)
                continue
            if token == "\x1b[B":  # down
                if selected < len(choices) - 1:
                    selected += 1
                    _redraw(stdout, choices, selected, prompt, buffer.text, use_color)
                continue

            if token == "\x03":  # Ctrl-C
                raise KeyboardInterrupt
            if token == "\x04":  # Ctrl-D — only exits on an empty buffer
                if not buffer.text:
                    raise EOFError
                continue

            if token in ("\x7f", "\x08"):  # Backspace / Ctrl-H
                width = buffer.backspace()
                if width:
                    _write(stdout, "\b" * width + " " * width + "\b" * width)
                continue

            if _is_printable(token):
                # Typing = choosing "say it yourself": jump the highlight to
                # the free option and start/continue the prompt buffer.
                if selected != len(choices) - 1:
                    selected = len(choices) - 1
                    _redraw(stdout, choices, selected, prompt, buffer.text, use_color)
                buffer.append(token)
                _write(stdout, token)
                continue

            # Other control characters: ignore.


def _write_block(
    stdout: IO,
    choices: list[SuggestionChoice],
    selected: int,
    prompt: str,
    buffer_text: str,
    use_color: bool,
) -> None:
    """Print the suggestion block, erasing each line before writing it.

    The `\r` + whole-line erase on every line is what keeps the list's left
    edge pinned to column 2 across redraws — a shorter line can never leave
    a stale fragment that makes the rows look misaligned.
    """
    lines = render_choices_block(
        choices, selected, prompt, use_color, buffer_text
    ).split("\n")
    for line in lines[:-1]:
        _write(stdout, "\r" + _ERASE_LINE + line + "\n")
    _write(stdout, "\r" + _ERASE_LINE + lines[-1])


def _redraw(
    stdout: IO,
    choices: list[SuggestionChoice],
    selected: int,
    prompt: str,
    buffer_text: str,
    use_color: bool,
) -> None:
    """Move back to the top of the block and re-render it in place.

    The cursor sits on the prompt line, which is `len(choices)` lines below
    the first list line — so we move up exactly `len(choices)`, NOT
    `len(choices) + 1`. The extra line would land one row above the block:
    every redraw would shift the whole list up a row and leave the old
    prompt line behind, stacking "> "s and creeping over the text above.
    """
    _write(stdout, f"\033[{len(choices)}A\r")
    _write_block(stdout, choices, selected, prompt, buffer_text, use_color)


def _commit(
    stdout: IO, choices: list[SuggestionChoice], prompt: str, text: str
) -> None:
    """Erase the block and echo the submitted line like a typed one."""
    _clear_block(stdout, len(choices))
    _write(stdout, prompt + text)


def _clear_block(stdout: IO, n_choices: int) -> None:
    """Erase the rendered suggestion block and park the cursor at its top.

    The block occupies n_choices list lines + 1 prompt line; the cursor is
    on the prompt line. Move up n_choices to the first list line, erase all
    n_choices + 1 lines, then come back up so the next output replaces the
    block instead of piling below it.
    """
    _write(stdout, f"\033[{n_choices}A\r")
    for _ in range(n_choices + 1):
        _write(stdout, _ERASE_LINE + "\n")
    _write(stdout, f"\033[{n_choices + 1}A\r")


# ── raw byte reader ───────────────────────────────────────────────────────


_ARROW_TOKENS = {
    b"\x1b[A": "\x1b[A",  # CSI Up
    b"\x1b[B": "\x1b[B",  # CSI Down
    b"\x1bOA": "\x1b[A",  # SS3 Up (application-cursor mode)
    b"\x1bOB": "\x1b[B",  # SS3 Down
}


def _read_loop(fd: int, stdout: IO, initial: str = "") -> str:
    """Core read/echo loop, driven directly off the tty fd.

    We use `os.read` on the raw fd so multi-byte UTF-8 sequences arrive
    intact — TextIO layered over a raw-mode tty can decode-fail mid-glyph
    when a paste arrives faster than we can consume it.

    `initial` seeds the buffer (used when a keystroke dismisses the
    suggestion list and becomes the first typed character).
    """
    line = _Line()
    for ch in initial:
        line.append(ch)
        _write(stdout, ch)
    decoder = _Utf8Decoder()

    while True:
        try:
            data = os.read(fd, 32)
        except OSError:
            # Interrupted read etc.
            data = b""
        if not data:
            if line.text:
                return line.text
            raise EOFError

        for ch in decoder.feed(data):
            if ch.startswith("\x1b"):
                # ANSI escape sequence (arrow keys, …) — not text; swallow.
                continue

            code = ord(ch)

            if ch in ("\r", "\n"):
                return line.text

            if code == 0x03:  # Ctrl-C
                raise KeyboardInterrupt

            if code == 0x04:  # Ctrl-D
                if not line.text:
                    raise EOFError
                continue

            if code in (0x7F, 0x08):  # DEL / Ctrl-H
                width = line.backspace()
                if width:
                    _write(stdout, "\b" * width + " " * width + "\b" * width)
                continue

            if code == 0x1B:
                # Defensive: the decoder already drains ESC sequences at the
                # byte layer, so we shouldn't see one here. Ignore any that
                # slip through (e.g. an unterminated ESC at end-of-read).
                continue

            if code < 0x20:
                # Other control chars (Ctrl-A/E/K, Tab, …). Skip — we're
                # not a full-featured editor, just enough to type safely.
                continue

            line.append(ch)
            _write(stdout, ch)


class _Utf8Decoder:
    """Byte-stream → codepoint iterator with built-in ESC-sequence handling.

    ANSI escape sequences (arrow keys, function keys) arrive as
    `ESC [ ...` or `ESC O ...` on macOS Terminal, iTerm2, and tmux. Arrow
    keys are surfaced to the caller as tokens (`"\x1b[A"` etc.) so suggest
    mode can react to them; every other sequence is drained at the byte
    layer so the caller never sees its intermediate bytes. A bare ESC (with
    no follower in the same read chunk) is dropped rather than yielded — it
    would only ever mean Alt-<key> or a partial press, neither of which
    belongs in the buffer.
    """

    def __init__(self) -> None:
        self._buf = bytearray()
        # None = normal; "after_esc" = ESC seen, awaiting introducer;
        # "csi" = draining the tail of a CSI/SS3 sequence.
        self._esc: str | None = None
        self._csi = bytearray()

    def feed(self, data: bytes):
        i = 0
        while i < len(data):
            b = data[i]

            if self._esc == "after_esc":
                # First byte after ESC: `[` (CSI) or `O` (SS3) opens a
                # multi-byte sequence; anything else is a bare ESC / Alt-<key>
                # that we discard.
                if b in (0x5B, 0x4F):  # '[' or 'O'
                    self._esc = "csi"
                    self._csi = bytearray(b"\x1b" + bytes([b]))
                else:
                    self._esc = None
                i += 1
                continue
            if self._esc == "csi":
                # CSI/SS3 terminates at any byte in 0x40..0x7e.
                self._csi.append(b)
                if 0x40 <= b <= 0x7E:
                    self._esc = None
                    token = _ARROW_TOKENS.get(bytes(self._csi))
                    if token is not None:
                        yield token
                i += 1
                continue

            if b == 0x1B:
                # Enter ESC state; drop any half-decoded bytes just in case.
                self._esc = "after_esc"
                self._buf.clear()
                i += 1
                continue

            self._buf.append(b)
            try:
                s = self._buf.decode("utf-8")
            except UnicodeDecodeError as exc:
                if exc.start > 0:
                    good = bytes(self._buf[: exc.start]).decode("utf-8")
                    self._buf = bytearray(self._buf[exc.start :])
                    for ch in good:
                        yield ch
                i += 1
                continue
            self._buf.clear()
            for ch in s:
                yield ch
            i += 1
