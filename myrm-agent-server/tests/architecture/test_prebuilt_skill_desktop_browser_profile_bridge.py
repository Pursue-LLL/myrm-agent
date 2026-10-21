"""Architecture guard tests for desktop-browser-profile-bridge prebuilt skill."""

from pathlib import Path

_SERVER_ROOT = Path(__file__).resolve().parents[2]
_SKILL_MD = _SERVER_ROOT / "assets" / "prebuilt_skills" / "desktop-browser-profile-bridge" / "SKILL.md"


def test_prebuilt_skill_desktop_browser_profile_bridge_structure():
    assert _SKILL_MD.exists(), f"Skill file not found at {_SKILL_MD}"

    content = _SKILL_MD.read_text(encoding="utf-8")
    assert content.startswith("---"), "Must start with frontmatter"
    assert "name: desktop-browser-profile-bridge" in content
    assert "profile-bridge" in content
    assert "session-reuse" in content
    assert "Zero Raw Master Key Export" in content
    assert "Read-Only SQLite Clone" in content
    assert "Ephemeral Profile Snapshot" in content
    assert "Driver Attachment & Validation" in content
    assert len(content.splitlines()) < 500, "Must be under 500 lines"
