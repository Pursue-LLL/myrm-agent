"""Architecture guard tests for skill-evolution-patcher prebuilt skill."""

from pathlib import Path

_SERVER_ROOT = Path(__file__).resolve().parents[2]
_SKILL_MD = _SERVER_ROOT / "assets" / "prebuilt_skills" / "skill-evolution-patcher" / "SKILL.md"


def test_prebuilt_skill_evolution_patcher_structure():
    assert _SKILL_MD.exists(), f"Skill file not found at {_SKILL_MD}"

    content = _SKILL_MD.read_text(encoding="utf-8")
    assert content.startswith("---"), "Must start with frontmatter"
    assert "name: skill-evolution-patcher" in content
    assert "self-evolution" in content
    assert "rule-patching" in content
    assert "Intent Capture" in content
    assert "Atomic Patch Generation" in content
    assert "In-Place Rule Patching" in content
    assert "Hot-Reload" in content
    assert "Tool Privilege Escalation Prohibited" in content
    assert len(content.splitlines()) < 500, "Must be under 500 lines"
