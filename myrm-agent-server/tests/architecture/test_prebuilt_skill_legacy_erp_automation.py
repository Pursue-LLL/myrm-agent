"""Architecture guard: legacy-erp-automation skill must preserve its core operating contract.

[INPUT]
- assets/prebuilt_skills/legacy-erp-automation/SKILL.md

[OUTPUT]
- Architecture tests ensuring the legacy ERP skill retains snapshot-first
  discipline, vault-only login, vision fallback, delivery verification, and
  unattended stop rules.
"""

from __future__ import annotations

from pathlib import Path

_SKILL_MD = (
    Path(__file__).resolve().parents[2]
    / "assets"
    / "prebuilt_skills"
    / "legacy-erp-automation"
    / "SKILL.md"
)


def _text() -> str:
    return _SKILL_MD.read_text(encoding="utf-8")


def test_skill_file_exists() -> None:
    assert _SKILL_MD.exists()


def test_allowed_tools_are_snapshot_interact_vision_scoped() -> None:
    text = _text()
    for tool in (
        "desktop_snapshot_tool",
        "desktop_interact_tool",
        "desktop_vision_tool",
        "file_read_tool",
        "file_write_tool",
    ):
        assert tool in text


def test_snapshot_first_discipline() -> None:
    text = _text()
    assert "Snapshot First" in text
    assert "desktop_snapshot_tool" in text


def test_vault_only_login() -> None:
    text = _text()
    assert "fill_credential" in text
    assert "never type" in text.lower() or "never typed" in text.lower()


def test_delivery_verification_required() -> None:
    text = _text()
    assert "Delivery Verification" in text


def test_unattended_stop_rule() -> None:
    text = _text()
    assert "human review" in text.lower()
