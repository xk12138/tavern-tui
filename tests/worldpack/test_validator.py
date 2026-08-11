"""Tests for the rule engine.

One test per rule ID, each with at least a positive-passing and a
negative-triggering path. Fixtures under tests/fixtures/ cover the common
cases; anything hyper-specific is inlined via tmp_path.
"""

from pathlib import Path

from tavern.worldpack.validator import validate_worldpack


# ── happy paths ──────────────────────────────────────────────────────────


def test_full_ok_has_no_errors_or_warnings(FIXTURES_DIR):
    report = validate_worldpack(FIXTURES_DIR / "full-ok")
    assert report.ok is True
    assert report.errors == []
    assert report.warnings == []


def test_minimal_ok_has_no_errors(FIXTURES_DIR):
    # Minimal is missing templates/intro/npcs on purpose — warnings expected.
    report = validate_worldpack(FIXTURES_DIR / "minimal-ok" / "world.toml")
    assert report.ok is True
    assert report.errors == []
    warn_codes = {d.code for d in report.warnings}
    # Minimal fixture omits templates but has intro-via-description via world.
    # It should at least trigger W006 (no templates).
    assert "W006" in warn_codes


# ── error rules ──────────────────────────────────────────────────────────


def test_E001_missing_path(tmp_path):
    report = validate_worldpack(tmp_path / "nope")
    assert report.ok is False
    assert any(d.code == "E001" for d in report.errors)


def test_E003_broken_toml(FIXTURES_DIR):
    report = validate_worldpack(FIXTURES_DIR / "broken-toml" / "world.toml")
    assert report.ok is False
    assert any(d.code == "E003" for d in report.errors)


def test_E004_missing_setting_and_initial_tavern(FIXTURES_DIR):
    report = validate_worldpack(
        FIXTURES_DIR / "missing-required" / "world.toml"
    )
    codes = {d.code for d in report.errors}
    assert "E004" in codes


def test_E005_bad_slug(tmp_path: Path):
    (tmp_path / "world.toml").write_text(
        '[world]\nid="Bad Slug!"\nname="X"\nversion="0.1.0"\n'
        '[world.setting]\nera="x"\ntone="x"\n'
        '[world.initial_tavern]\nname="a"\nlocation="b"\n'
        'description="c"\nopening_hook="' + "hook " * 20 + '"\n',
        encoding="utf-8",
    )
    report = validate_worldpack(tmp_path / "world.toml")
    codes = {d.code for d in report.errors}
    assert "E005" in codes


def test_E006_bad_semver(tmp_path: Path):
    (tmp_path / "world.toml").write_text(
        '[world]\nid="ok"\nname="X"\nversion="notasemver"\n'
        '[world.setting]\nera="x"\ntone="x"\n'
        '[world.initial_tavern]\nname="a"\nlocation="b"\n'
        'description="c"\nopening_hook="' + "hook " * 20 + '"\n',
        encoding="utf-8",
    )
    report = validate_worldpack(tmp_path / "world.toml")
    codes = {d.code for d in report.errors}
    assert "E006" in codes


def test_E007_bad_present_npc_ref(FIXTURES_DIR):
    report = validate_worldpack(FIXTURES_DIR / "bad-ref" / "world.toml")
    codes = {d.code for d in report.errors}
    assert "E007" in codes


def test_E010_hp_current_exceeds_max(tmp_path: Path):
    (tmp_path / "templates").mkdir()
    (tmp_path / "world.toml").write_text(
        '[world]\nid="hp"\nname="HP"\nversion="0.1.0"\n'
        '[world.setting]\nera="x"\ntone="x"\n'
        '[world.initial_tavern]\nname="a"\nlocation="b"\n'
        'description="c"\nopening_hook="' + "hook " * 20 + '"\n',
        encoding="utf-8",
    )
    (tmp_path / "templates" / "reckless.toml").write_text(
        '[template]\nname="reckless"\n'
        '[template.pc.hp]\ncurrent=20\nmax=10\n',
        encoding="utf-8",
    )
    report = validate_worldpack(tmp_path)
    assert any(d.code == "E010" for d in report.errors)


# ── warning rules ────────────────────────────────────────────────────────


def test_W002_no_factions(FIXTURES_DIR):
    report = validate_worldpack(FIXTURES_DIR / "no-factions" / "world.toml")
    warn_codes = {d.code for d in report.warnings}
    assert "W002" in warn_codes
    # not a failure
    assert report.ok is True


def test_W003_no_timeline(FIXTURES_DIR):
    report = validate_worldpack(FIXTURES_DIR / "no-factions" / "world.toml")
    warn_codes = {d.code for d in report.warnings}
    assert "W003" in warn_codes


def test_W005_over_token_budget(tmp_path: Path):
    # 8000-token threshold; CJK weighted ~0.6/char so 15000 chars ≈ 9000 tokens.
    huge = "内力" * 8000
    (tmp_path / "world.toml").write_text(
        f'[world]\nid="big"\nname="Big"\nversion="0.1.0"\n'
        f'[world.setting]\nera="x"\ntone="x"\n'
        f'[world.rules]\nsummary="""\n{huge}\n"""\n'
        f'[world.initial_tavern]\nname="a"\nlocation="b"\n'
        f'description="c"\nopening_hook="' + "hook " * 20 + '"\n',
        encoding="utf-8",
    )
    report = validate_worldpack(tmp_path / "world.toml")
    warn_codes = {d.code for d in report.warnings}
    assert "W005" in warn_codes


def test_W008_short_opening_hook(tmp_path: Path):
    (tmp_path / "world.toml").write_text(
        '[world]\nid="short"\nname="Short"\nversion="0.1.0"\n'
        '[world.setting]\nera="x"\ntone="x"\n'
        '[world.initial_tavern]\nname="a"\nlocation="b"\n'
        'description="c"\nopening_hook="too short"\n',
        encoding="utf-8",
    )
    report = validate_worldpack(tmp_path / "world.toml")
    warn_codes = {d.code for d in report.warnings}
    assert "W008" in warn_codes


def test_W009_npc_missing_goals_or_secrets(tmp_path: Path):
    (tmp_path / "npcs").mkdir()
    (tmp_path / "world.toml").write_text(
        '[world]\nid="w9"\nname="W9"\nversion="0.1.0"\n'
        '[world.setting]\nera="x"\ntone="x"\n'
        '[world.initial_tavern]\nname="a"\nlocation="b"\n'
        'description="c"\nopening_hook="' + "hook " * 20 + '"\n',
        encoding="utf-8",
    )
    (tmp_path / "npcs" / "hollow.toml").write_text(
        '[npc]\nid="hollow"\nname="Hollow"\n[npc.card]\n',
        encoding="utf-8",
    )
    report = validate_worldpack(tmp_path)
    warn_codes = [d.code for d in report.warnings]
    # W009 should fire for both goals and secrets missing
    assert warn_codes.count("W009") == 2


# ── strict mode combines error+warning into pass/fail ────────────────────


def test_strict_mode_semantics_in_report(FIXTURES_DIR):
    report = validate_worldpack(FIXTURES_DIR / "no-factions" / "world.toml")
    # Report itself is only about errors; --strict adjustment happens in CLI.
    assert report.ok is True
    assert report.warnings, "expected non-empty warnings from fixture"


# ── informational stats always present ───────────────────────────────────


def test_stats_infodiag_attached(FIXTURES_DIR):
    report = validate_worldpack(FIXTURES_DIR / "full-ok")
    assert any(d.code == "I001" for d in report.diagnostics)
