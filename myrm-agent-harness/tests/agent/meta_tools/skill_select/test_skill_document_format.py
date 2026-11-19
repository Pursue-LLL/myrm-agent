"""The skill document the model receives has no frontmatter and always starts with a title."""

from __future__ import annotations

from unittest.mock import AsyncMock

from myrm_agent_harness.agent.meta_tools.skills.select.skill_document_loader import get_skill_document
from myrm_agent_harness.backends.skills.types import SkillMetadata


async def _document(sop: str) -> str:
    backend = AsyncMock()
    backend.get_skill_content.return_value = sop
    backend.list_skill_resources.return_value = []
    skill = SkillMetadata(name="demo", description="demo skill", storage_skill_id="demo")
    return await get_skill_document(skill, backend)


async def test_the_frontmatter_is_not_part_of_the_document() -> None:
    document = await _document("---\nname: test\ndescription: hello\n---\n# My Skill\n\nDo stuff.")

    assert document.startswith("# My Skill")
    assert "description: hello" not in document


async def test_a_document_without_a_heading_gets_the_skill_name_as_its_title() -> None:
    document = await _document("Just some content without a heading.")

    assert document.startswith("# demo\n\nJust some content without a heading.")
