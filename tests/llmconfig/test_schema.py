"""Schema helpers: mask_secret + is_secret_field."""

from __future__ import annotations

from tavern.llmconfig.schema import (
    LLM_ROLES,
    UIConfig,
    coerce_ui,
    is_secret_field,
    mask_secret,
)


def test_mask_empty():
    assert mask_secret("") == ""


def test_mask_very_short():
    assert mask_secret("x") == "***"
    assert mask_secret("abcdefg") == "***"  # 7 chars, still under 8


def test_mask_normal():
    assert mask_secret("sk-ant-abcd1234efgh") == "sk-a...efgh"


def test_mask_exactly_8():
    # 8 chars: 4 + ... + 4 (they overlap but the format still applies)
    assert mask_secret("12345678") == "1234...5678"


def test_secret_field_detection():
    assert is_secret_field("api_key")
    assert is_secret_field("apiKey")
    assert is_secret_field("APIKEY")
    assert is_secret_field("AUTH_TOKEN")
    assert is_secret_field("password")
    assert is_secret_field("SECRET_SAUCE")
    assert not is_secret_field("provider")
    assert not is_secret_field("model")
    assert not is_secret_field("base_url")


def test_suggest_role_is_known():
    assert "suggest" in LLM_ROLES


def test_ui_suggestions_default_on():
    assert UIConfig().suggestions is True


def test_coerce_ui_suggestions_bool():
    assert coerce_ui({"suggestions": False}).suggestions is False
    assert coerce_ui({"suggestions": "no"}).suggestions is True  # non-bool ignored
    assert coerce_ui(None).suggestions is True
