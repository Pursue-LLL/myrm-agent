"""Unit tests for the web-project-seo-optimization prebuilt skill and seo_weekly_audit cron blueprint."""

from __future__ import annotations

from pathlib import Path

import pytest
from myrm_agent_harness.backends.skills._runtime import build_skill_metadata
from myrm_agent_harness.backends.skills._utils import parse_skill_frontmatter
from myrm_agent_harness.backends.skills.types import SkillTrust

from app.core.cron.blueprints import (
    BUILTIN_BLUEPRINTS,
    BlueprintFillError,
    fill_blueprint,
    get_blueprint,
)
from app.services.agent.builtin_specs.vertical import _VERTICAL_BUILTIN_AGENTS


def test_web_project_seo_optimization_frontmatter_parse() -> None:
    """Verify web-project-seo-optimization SKILL.md parses cleanly and adheres to agentskills spec."""
    skill_path = (
        Path(__file__).resolve().parents[3]
        / "assets"
        / "prebuilt_skills"
        / "web-project-seo-optimization"
        / "SKILL.md"
    )
    assert skill_path.exists(), f"Skill file not found at {skill_path}"

    content = skill_path.read_text(encoding="utf-8")
    frontmatter = parse_skill_frontmatter(content)

    assert frontmatter.name == "web-project-seo-optimization"
    assert frontmatter.category == "marketing-growth"
    assert "seo" in frontmatter.tags
    assert "llmo" in frontmatter.tags
    assert frontmatter.contract is not None
    assert len(frontmatter.contract.steps) == 5
    assert len(frontmatter.contract.potential_traps) >= 3
    assert len(frontmatter.contract.verification_steps) >= 2

    # Build runtime metadata
    meta = build_skill_metadata(
        frontmatter=frontmatter,
        skill_content=content,
        skill_name=frontmatter.name,
        storage_path=str(skill_path.parent),
        trust=SkillTrust.TRUSTED,
    )
    assert meta.name == "web-project-seo-optimization"
    assert meta.description != ""
    assert "browser_navigate_tool" in (meta.allowed_tools or [])


def test_builtin_seo_agent_has_web_project_seo_skill() -> None:
    """Verify builtin-seo Agent has web-project-seo-optimization bound by default."""
    seo_agent = next((a for a in _VERTICAL_BUILTIN_AGENTS if a.id == "builtin-seo"), None)
    assert seo_agent is not None
    assert "web-project-seo-optimization" in seo_agent.default_skill_ids


def test_seo_weekly_audit_blueprint_registered() -> None:
    """Verify seo_weekly_audit is registered in BUILTIN_BLUEPRINTS."""
    bp = get_blueprint("seo_weekly_audit")
    assert bp is not None
    assert bp.id == "seo_weekly_audit"
    assert bp.category == "marketing-growth"
    assert "en" in bp.title and "zh" in bp.title and "ja" in bp.title
    assert "target_url" in [s.name for s in bp.slots]
    assert "depth" in [s.name for s in bp.slots]


def test_seo_weekly_audit_blueprint_fill_valid() -> None:
    """Verify seo_weekly_audit can be materialized with valid parameters."""
    result = fill_blueprint(
        "seo_weekly_audit",
        {
            "target_url": "https://mysite.com",
            "depth": "deep",
            "time": "08:30",
            "day": "1",
        },
        locale="zh",
    )
    assert result is not None
    assert result.schedule.expr == "30 8 * * 1"
    assert "https://mysite.com" in result.prompt
    assert "deep" in result.prompt
    assert "SEO" in result.name


def test_seo_weekly_audit_blueprint_fill_invalid_depth() -> None:
    """Verify invalid depth option raises BlueprintFillError."""
    with pytest.raises(BlueprintFillError, match="depth='ultra_deep' not allowed"):
        fill_blueprint(
            "seo_weekly_audit",
            {
                "target_url": "https://mysite.com",
                "depth": "ultra_deep",
                "time": "08:30",
                "day": "1",
            },
        )
