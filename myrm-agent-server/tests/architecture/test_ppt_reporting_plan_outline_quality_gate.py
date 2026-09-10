"""Tests for PPT Reporting Plan Outline Quality Gate in office-document skill and subagents."""

from pathlib import Path

import yaml


def test_office_document_skill_has_ppt_reporting_outline_quality_gate() -> None:
    skill_path = (
        Path(__file__).resolve().parents[2]
        / "assets"
        / "prebuilt_skills"
        / "office-document"
        / "SKILL.md"
    )
    assert skill_path.exists(), f"SKILL.md not found at {skill_path}"
    content = skill_path.read_text(encoding="utf-8")

    # 验证四大质量门禁
    assert "Reporting PPT Outline Quality Gate" in content
    assert "Gate 1: Action-Oriented Takeaway Headlines" in content
    assert "Gate 2: 16:9 Visual Container Layout Specification" in content
    assert "Gate 3: Quantified Metric Evidence" in content
    assert "Gate 4: Anti-Wall-of-Text & Clean Typography" in content
    assert "hero_metric_cards" in content
    assert "split_comparison" in content
    assert "card_grid_3col" in content
    assert "sequential_chevron_process" in content


def test_structure_planner_subagent_has_reporting_slide_gate() -> None:
    config_path = (
        Path(__file__).resolve().parents[2]
        / "app"
        / "config"
        / "subagents"
        / "core"
        / "structure-planner.yaml"
    )
    assert config_path.exists()
    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    prompt = data.get("system_prompt", "")
    assert "Reporting Slide Outline Quality Gate" in prompt
    assert "Action Headlines" in prompt
    assert "16:9 container layouts" in prompt


def test_format_verifier_subagent_has_takeaway_headline_gate() -> None:
    config_path = (
        Path(__file__).resolve().parents[2]
        / "app"
        / "config"
        / "subagents"
        / "core"
        / "format-verifier.yaml"
    )
    assert config_path.exists()
    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    prompt = data.get("system_prompt", "")
    assert "Takeaway headline gate" in prompt
    assert "16:9 container architecture" in prompt
    assert "Anti-wall-of-text & emoji ban" in prompt
