"""Architecture guard tests for skill-evolution-patcher prebuilt skill."""

from pathlib import Path


def _find_repo_root() -> Path:
    current = Path(__file__).resolve().parent
    for p in [current, *current.parents]:
        if (p / "myrm-agent").is_dir() or (p / "assets").is_dir():
            return p
    return current.parent.parent


def test_prebuilt_skill_evolution_patcher_structure():
    repo_root = _find_repo_root()
    skill_path = repo_root / "assets" / "prebuilt_skills" / "skill-evolution-patcher" / "SKILL.md"
    if not skill_path.exists():
        skill_path = (
            repo_root
            / "myrm-agent"
            / "myrm-agent-server"
            / "assets"
            / "prebuilt_skills"
            / "skill-evolution-patcher"
            / "SKILL.md"
        )
    assert skill_path.exists(), f"Skill file not found at {skill_path}"

    content = skill_path.read_text(encoding="utf-8")
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
