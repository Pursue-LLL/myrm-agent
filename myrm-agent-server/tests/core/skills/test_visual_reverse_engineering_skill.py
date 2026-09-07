"""Unit and integration test for visual-reverse-engineering prebuilt skill.

Verifies:
1. Valid SKILL.md YAML frontmatter parsing.
2. Compliance with required contract steps, traps, and verification steps.
3. 4-step reverse engineering methodology inclusion in instructions.
4. Clean discovery and loading via SkillsService.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from myrm_agent_harness.agent.skills.market.sanitizer import SKILL_MD_FILE
from myrm_agent_harness.toolkits.storage.local import LocalStorageBackend

from app.core.skills import prebuilt_sync
from app.core.skills.store.service import SkillsService


def test_visual_reverse_engineering_frontmatter_validity() -> None:
    skill_path = (
        Path(__file__).resolve().parents[3]
        / "assets"
        / "prebuilt_skills"
        / "visual-reverse-engineering"
        / SKILL_MD_FILE
    )
    assert skill_path.exists(), f"Skill file not found at {skill_path}"

    content = skill_path.read_text(encoding="utf-8")
    assert content.startswith("---"), "SKILL.md must start with YAML frontmatter"

    parts = content.split("---", 2)
    assert len(parts) >= 3, "Invalid frontmatter structure"

    frontmatter = yaml.safe_load(parts[1])
    assert frontmatter["name"] == "visual-reverse-engineering"
    assert frontmatter["version"] == "1.0.0"
    assert "contract" in frontmatter

    contract = frontmatter["contract"]
    assert len(contract.get("steps", [])) == 5
    assert len(contract.get("potential_traps", [])) >= 3
    assert len(contract.get("verification_steps", [])) >= 2

    # Verify 4-step paradigm in markdown instructions
    body = parts[2]
    assert "Datum Plane & Spine Anchor" in body
    assert "Topological Graph Extraction" in body
    assert "Datum Scale Factor Derivation" in body
    assert "Non-Orthogonal Angle & Geometry Projection" in body


@pytest.mark.asyncio
async def test_visual_reverse_engineering_discovered_in_sync(tmp_path: Path) -> None:
    storage = LocalStorageBackend(str(tmp_path))
    service = SkillsService(storage=storage)

    sync_result = await prebuilt_sync.sync_prebuilt_seeds(service.storage)
    assert "visual-reverse-engineering" in sync_result.skill_ids

    skill = await service.get_skill("visual-reverse-engineering")
    assert skill is not None
    assert skill.name == "visual-reverse-engineering"
    assert "vision" in skill.tags
    assert "topology" in skill.tags
