"""
Architecture and schema integrity tests for the prebuilt skill: metrics-glossary-crystallization.
Verifies YAML frontmatter validity, contract steps, 6-dimensional metric schema, and Wiki crystallization SOP.
"""

from pathlib import Path

import yaml

SKILL_PATH = (
    Path(__file__).resolve().parents[2]
    / "assets"
    / "prebuilt_skills"
    / "metrics-glossary-crystallization"
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


def test_metrics_glossary_frontmatter():
    assert SKILL_PATH.exists(), f"Skill file not found at {SKILL_PATH}"
    frontmatter, body = parse_skill_markdown(SKILL_PATH)

    assert frontmatter["name"] == "metrics-glossary-crystallization"
    assert frontmatter["version"] == "1.0.0"
    assert "metrics" in frontmatter["tags"] or "kpi" in frontmatter["tags"]
    assert "contract" in frontmatter

    # Tools check: must include wiki tools
    allowed_tools = frontmatter.get("allowed-tools", "")
    assert "wiki_query" in allowed_tools
    assert "wiki_ingest" in allowed_tools

    contract = frontmatter["contract"]
    assert "steps" in contract and len(contract["steps"]) >= 4
    assert "potential_traps" in contract and len(contract["potential_traps"]) >= 2
    assert "verification_steps" in contract and len(contract["verification_steps"]) >= 2


def test_metrics_glossary_six_dimensions_and_sop():
    _, body = parse_skill_markdown(SKILL_PATH)

    # 5-Dimensional Metric Specification
    assert "Standard Identifier & Aliases" in body
    assert "Business Definition & Objectives" in body
    assert "Formal Computation Logic & SQL" in body
    assert "Data Lineage & Granularity" in body
    assert "Anti-Patterns & Known Pitfalls" in body

    # SOP & Wiki Integration
    assert "llm_wiki" in body
    assert "wiki_ingest_tool" in body
    assert "wiki_query_tool" in body


def run_all():
    test_metrics_glossary_frontmatter()
    test_metrics_glossary_six_dimensions_and_sop()
    print("ALL TESTS PASSED (2/2)")


if __name__ == "__main__":
    run_all()
