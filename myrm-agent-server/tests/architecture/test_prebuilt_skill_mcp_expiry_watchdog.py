"""Architecture test for mcp-expiry-watchdog prebuilt skill asset."""

from __future__ import annotations

from pathlib import Path

import yaml

_SERVER_ROOT = Path(__file__).resolve().parents[2]
SKILL_PATH = _SERVER_ROOT / "assets" / "prebuilt_skills" / "mcp-expiry-watchdog" / "SKILL.md"


def test_mcp_expiry_watchdog_asset_structure() -> None:
    assert SKILL_PATH.exists(), f"Skill file does not exist at {SKILL_PATH}"

    raw_text = SKILL_PATH.read_text(encoding="utf-8")
    parts = raw_text.split("---", 2)
    assert len(parts) >= 3, "Skill file must contain YAML frontmatter delimited by ---"

    frontmatter = yaml.safe_load(parts[1])
    assert frontmatter["name"] == "mcp-expiry-watchdog"
    assert "description" in frontmatter and len(frontmatter["description"]) > 10
    assert frontmatter["version"] == "1.0.0"
    assert frontmatter["category"] == "engineering"
    assert "allowed-tools" in frontmatter

    body = parts[2]
    # Check 4 phases exist
    assert "Phase 1: Credential Expiry Inspection" in body
    assert "Phase 2: Proactive Health & Expiry Gating" in body
    assert "Phase 3: Silent Pre-Flight Token Refresh" in body
    assert "Phase 4: HITL Re-authentication Alerting" in body

    # Check contracts and thresholds
    assert "CRITICAL" in body
    assert "WARN_REFRESHABLE" in body
    assert "/settings/integrations" in body
