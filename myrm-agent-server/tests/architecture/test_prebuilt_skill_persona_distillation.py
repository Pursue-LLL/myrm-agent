"""
Architecture and schema integrity tests for the prebuilt skill: persona-corpus-distillation.
Verifies YAML frontmatter validity, contract steps, 4-pillar cognitive matrix, and dual-artifact specification.
"""

from pathlib import Path

import yaml

SKILL_PATH = (
    Path(__file__).resolve().parents[2]
    / "assets"
    / "prebuilt_skills"
    / "persona-corpus-distillation"
    / "SKILL.md"
)


def parse_skill_markdown(path: Path):
    content = path.read_text(encoding="utf-8")
    assert content.startswith("---"), "SKILL.md must start with YAML frontmatter"
    parts = content.split("---", 2)
    assert len(parts) >= 3, "SKILL.md must contain valid closing frontmatter"
    frontmatter = yaml.safe_load(parts[1])
    body = parts[2]
    return frontmatter, body


def test_persona_corpus_distillation_frontmatter():
    assert SKILL_PATH.exists(), f"Skill file not found at {SKILL_PATH}"
    frontmatter, body = parse_skill_markdown(SKILL_PATH)

    assert frontmatter["name"] == "persona-corpus-distillation"
    assert frontmatter["version"] == "1.0.0"
    assert "persona" in frontmatter["tags"] or "persona-distillation" in frontmatter["tags"]
    assert "contract" in frontmatter

    contract = frontmatter["contract"]
    assert "steps" in contract and len(contract["steps"]) >= 4
    assert "potential_traps" in contract and len(contract["potential_traps"]) >= 2
    assert "verification_steps" in contract and len(contract["verification_steps"]) >= 2


def test_persona_corpus_distillation_cognitive_pillars():
    _, body = parse_skill_markdown(SKILL_PATH)

    # Core cognitive phases & dimensions
    assert "Decision Heuristics" in body
    assert "Mental Models" in body
    assert "Conversational Voice Fingerprint" in body
    assert "Golden Few-Shot Playbook" in body
    assert "Safety Guardrails" in body

    # Deliverables & quality standards
    assert "SKILL.md Packaging" in body
    assert "Anti-Hallucination" in body


def run_all():
    test_persona_corpus_distillation_frontmatter()
    test_persona_corpus_distillation_cognitive_pillars()
    print("ALL TESTS PASSED (2/2)")

if __name__ == "__main__":
    run_all()
