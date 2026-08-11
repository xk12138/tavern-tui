"""Cheap token estimator.

We only use this for warnings on prompt budget, so we intentionally avoid
pulling in a real tokenizer (tiktoken / anthropic tokenizer). The formula:

    tokens ≈ chinese_chars * 0.6 + non_chinese_chars * 0.25

approximates the ballpark of common tokenizers well enough for a warning.
"""

from __future__ import annotations

import math


def _is_cjk(ch: str) -> bool:
    code = ord(ch)
    return (
        0x4E00 <= code <= 0x9FFF        # CJK Unified Ideographs
        or 0x3400 <= code <= 0x4DBF     # CJK Ext A
        or 0x3040 <= code <= 0x30FF     # Hiragana + Katakana
        or 0xAC00 <= code <= 0xD7AF     # Hangul syllables
    )


def estimate_tokens(text: str) -> int:
    """Return a rough token estimate for a piece of text.

    Whitespace still counts (it does in real tokenizers too), but zero-length
    input returns 0.
    """
    if not text:
        return 0
    cjk = sum(1 for ch in text if _is_cjk(ch))
    other = len(text) - cjk
    return math.ceil(cjk * 0.6 + other * 0.25)
