from pathlib import Path

import yaml

_SKILL_PATH = (
    Path(__file__).resolve().parents[2]
    / "assets"
    / "prebuilt_skills"
    / "conversational-skill-evolution"
    / "SKILL.md"
)


def test_conversational_skill_evolution_file_exists():
    assert _SKILL_PATH.is_file(), f"SKILL.md not found at {_SKILL_PATH}"


def test_conversational_skill_evolution_frontmatter_contract():
    content = _SKILL_PATH.read_text(encoding="utf-8")
    parts = content.split("---")
    assert len(parts) >= 3, "Frontmatter must be enclosed in '---'"
    fm = yaml.safe_load(parts[1])

    assert fm["name"] == "conversational-skill-evolution"
    assert "skill-evolution" in fm["tags"]
    assert "contract" in fm
    assert len(fm["contract"]["steps"]) == 4
    assert len(fm["contract"]["potential_traps"]) >= 2
    assert len(fm["contract"]["verification_steps"]) >= 2


def test_conversational_skill_evolution_sop_structure():
    content = _SKILL_PATH.read_text(encoding="utf-8")
    assert "Phase 1: Intent Ingestion" in content
    assert "Phase 2: Patch Synthesis" in content
    assert "Phase 3: Pre-flight Audit" in content
    assert "Phase 4: In-place Hot-Reload" in content
    assert "技能自我进化已生效" in content
