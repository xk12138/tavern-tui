"""Tests for the token estimator.

The estimator is heuristic — we don't test exact numbers, only the invariants:
zero for empty, monotonic in content length, and CJK weights more than ASCII.
"""

from tavern.worldpack.tokens import estimate_tokens


def test_empty_is_zero():
    assert estimate_tokens("") == 0


def test_ascii_grows_with_length():
    short = estimate_tokens("hello")
    longer = estimate_tokens("hello hello hello hello")
    assert longer > short


def test_cjk_weighted_more_than_ascii():
    # Same character count, CJK should score higher than ASCII letters.
    ascii_est = estimate_tokens("a" * 20)
    cjk_est = estimate_tokens("你" * 20)
    assert cjk_est > ascii_est


def test_mixed_content_positive():
    assert estimate_tokens("Hello 世界") > 0
