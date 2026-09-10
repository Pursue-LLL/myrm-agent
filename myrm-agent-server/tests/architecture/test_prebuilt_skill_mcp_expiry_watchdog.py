"""Architecture test for mcp-expiry-watchdog prebuilt skill asset."""

from __future__ import annotations

from pathlib import Path
import yaml

SKILL_PATH = Path("assets/prebuilt_skills/mcp-expiry-watchdog/SKILL.md")


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
    # Check 4 tiers exist
    assert "Tier 1: Credential Discovery & Expiry Harvesting" in body
    assert "Tier 2: Expiry Risk Level Classification" in body
    assert "Tier 3: Silent Background Token Refresh" in body
    assert "Tier 4: Actionable Reauth Nudge & Pre-Flight Banner" in body

    # Check contracts and thresholds
    assert "time_to_live_sec" in body
    assert "CRITICAL" in body
    assert "WARNING" in body
    assert "/settings/credentials" in body
