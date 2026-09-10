"""Architecture guard: mcp-reauth-watchdog skill must preserve its core operating contract.

[INPUT]
- assets/prebuilt_skills/mcp-reauth-watchdog/SKILL.md

[OUTPUT]
- Architecture tests ensuring mcp-reauth-watchdog skill retains:
  1. 4-stage proactive reauth pipeline (Probing, Graded Gates, Silent/Interactive Refresh, Post-Verification).
  2. Graded expiry gate rules (SAFE >24h, WARNING 1h-24h, BLOCKED <=1h).
  3. Interactive Reauth Card specification.
  4. Security invariants preventing secret token logging.

[POS]
Architecture test verifying the operational integrity and contract stability of the mcp-reauth-watchdog prebuilt skill.
"""

from __future__ import annotations

from pathlib import Path
import pytest

_SKILL_MD = (
    Path(__file__).resolve().parents[2]
    / "assets"
    / "prebuilt_skills"
    / "mcp-reauth-watchdog"
    / "SKILL.md"
)

_CORE_REAUTH_MARKERS = (
    "mcp-reauth-watchdog",
    "Credential TTL & Lease Probing",
    "Graded Expiry Gate Evaluation",
    "Silent Refresh & Interactive Reauth",
    "Post-Refresh Health Verification",
)

_GATE_TIER_MARKERS = (
    "HEALTHY / SAFE",
    "EXPIRING SOON",
    "CRITICAL / EXPIRED",
    "Reauth Card",
)

_SECURITY_INVARIANT_MARKERS = (
    "Refreshed tokens must NEVER be logged to plaintext",
    "encrypted vault storage",
)


def test_mcp_reauth_watchdog_skill_file_exists() -> None:
    assert _SKILL_MD.is_file(), f"Skill file does not exist at {_SKILL_MD}"


def test_mcp_reauth_watchdog_pipeline_markers() -> None:
    content = _SKILL_MD.read_text(encoding="utf-8")
    for marker in _CORE_REAUTH_MARKERS:
        assert marker in content, f"Missing pipeline marker: {marker}"


def test_mcp_reauth_watchdog_tiers_and_invariants() -> None:
    content = _SKILL_MD.read_text(encoding="utf-8")
    for marker in _GATE_TIER_MARKERS:
        assert marker in content, f"Missing gate tier marker: {marker}"
    for marker in _SECURITY_INVARIANT_MARKERS:
        assert marker in content, f"Missing security invariant marker: {marker}"
