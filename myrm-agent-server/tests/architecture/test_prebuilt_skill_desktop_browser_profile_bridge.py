"""Architecture guard tests for desktop-browser-profile-bridge prebuilt skill."""

from pathlib import Path


def _find_repo_root() -> Path:
    current = Path(__file__).resolve().parent
    for p in [current, *current.parents]:
        if (p / "myrm-agent").is_dir() or (p / "assets").is_dir():
            return p
    return current.parent.parent


def test_prebuilt_skill_desktop_browser_profile_bridge_structure():
    repo_root = _find_repo_root()
    skill_path = repo_root / "assets" / "prebuilt_skills" / "desktop-browser-profile-bridge" / "SKILL.md"
    if not skill_path.exists():
        skill_path = (
            repo_root
            / "myrm-agent"
            / "myrm-agent-server"
            / "assets"
            / "prebuilt_skills"
            / "desktop-browser-profile-bridge"
            / "SKILL.md"
        )
    assert skill_path.exists(), f"Skill file not found at {skill_path}"

    content = skill_path.read_text(encoding="utf-8")
    assert content.startswith("---"), "Must start with frontmatter"
    assert "name: desktop-browser-profile-bridge" in content
    assert "profile-bridge" in content
    assert "session-reuse" in content
    assert "Zero Raw Master Key Export" in content
    assert "Read-Only SQLite Clone" in content
    assert "Ephemeral Profile Snapshot" in content
    assert "Driver Attachment & Validation" in content
    assert len(content.splitlines()) < 500, "Must be under 500 lines"
