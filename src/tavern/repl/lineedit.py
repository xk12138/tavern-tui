"""CJK-safe line editor for the play REPL.

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
"""

from __future__ import annotations

import os
import sys
import unicodedata
from typing import IO


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


def readline_wide(
    prompt: str = "",
    *,
    stdin: IO | None = None,
    stdout: IO | None = None,
) -> str:
    """Read a line from the user, correctly redrawing wide characters.

    Semantics match `input()`:
      - Returns the line without the trailing newline.
      - Raises `EOFError` on Ctrl-D at an empty line (or on stream EOF).
      - Raises `KeyboardInterrupt` on Ctrl-C.

    Falls back to `input()` when we can't put the terminal in raw mode
    (non-TTY, Windows, no `termios`), so piped input and CI keep working.
    """
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout

    if not _can_raw_mode(stdin, stdout):
        return input(prompt)

    import termios  # local — non-POSIX platforms don't blow up on module load
    import tty

    fd = stdin.fileno()
    old_attrs = termios.tcgetattr(fd)
    try:
        # Enter raw mode BEFORE writing the prompt so the terminal's cooked
        # line discipline never gets a chance to echo an incoming keystroke
        # with the wrong (1-column) backspace behavior.
        tty.setraw(fd, when=termios.TCSANOW)
        _write(stdout, prompt)
        return _read_loop(fd, stdout)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_attrs)
        # Always finish on a fresh line — raw mode ate the CR/LF echo.
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


def _read_loop(fd: int, stdout: IO) -> str:
    """Core read/echo loop, driven directly off the tty fd.

    We use `os.read` on the raw fd so multi-byte UTF-8 sequences arrive
    intact — TextIO layered over a raw-mode tty can decode-fail mid-glyph
    when a paste arrives faster than we can consume it.
    """
    line = _Line()
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
    """Byte-stream → codepoint iterator with built-in ESC-sequence draining.

    ANSI escape sequences (arrow keys, function keys) arrive as
    `ESC [ ...` or `ESC O ...` on macOS Terminal, iTerm2, and tmux. We
    consume the whole sequence at the byte layer so the caller never
    sees the intermediate bytes and can treat the stream as "just
    codepoints." A bare ESC (with no follower in the same read chunk)
    is dropped rather than yielded — it would only ever mean Alt-<key>
    or a partial press, neither of which belongs in the buffer.
    """

    def __init__(self) -> None:
        self._buf = bytearray()
        # None = normal; "after_esc" = ESC seen, awaiting introducer;
        # "csi" = draining the tail of a CSI/SS3 sequence.
        self._esc: str | None = None

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
                else:
                    self._esc = None
                i += 1
                continue
            if self._esc == "csi":
                # CSI/SS3 terminates at any byte in 0x40..0x7e.
                if 0x40 <= b <= 0x7E:
                    self._esc = None
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
