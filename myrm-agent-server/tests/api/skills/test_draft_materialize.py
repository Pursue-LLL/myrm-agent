"""SKILL.md written for approved drafts must stay parseable whatever the draft text contains."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.api.skills import parse_skill_frontmatter

from app.api.skills.draft_materialize import materialize_skill_draft
from app.api.skills.drafts import SkillDraftRecord

_HOSTILE_DESCRIPTION = 'Convert: C:\\temp\\new # files\nthen say "done"'


def _draft(*, description: str | None, content: str | None, trigger_condition: str | None = None) -> SkillDraftRecord:
    return SkillDraftRecord(
        id="draft-1",
        agent_id="default",
        chat_id=None,
        draft_type="skill_draft",
        name="convert files",
        description=description,
        trigger_condition=trigger_condition,
        skill_steps="1. Convert",
        content=content,
        status="PENDING",
        reviewed_at=None,
        created_at=datetime.now(UTC),
        approval_status="PENDING",
    )


async def _written_skill_md(draft: SkillDraftRecord) -> str:
    """Run materialization with the disk write stubbed out and return the SKILL.md it tried to save."""
    service = MagicMock()
    service.save_skill = AsyncMock(return_value=SimpleNamespace(success=False, error="stubbed"))
    with patch("app.core.skills.creation.service.skill_creation_service", service):
        await materialize_skill_draft(draft, None)
    return str(service.save_skill.await_args.kwargs["content"])


@pytest.mark.asyncio
async def test_form_draft_description_round_trips_through_the_skill_parser() -> None:
    skill_md = await _written_skill_md(_draft(description=_HOSTILE_DESCRIPTION, content=None))

    frontmatter = parse_skill_frontmatter(skill_md, "convert-files")

    assert frontmatter.description == _HOSTILE_DESCRIPTION


@pytest.mark.asyncio
async def test_body_without_frontmatter_gets_a_parseable_description() -> None:
    skill_md = await _written_skill_md(_draft(description=_HOSTILE_DESCRIPTION, content="# Convert\nSteps here"))

    frontmatter = parse_skill_frontmatter(skill_md, "convert-files")

    assert frontmatter.description == _HOSTILE_DESCRIPTION
    assert skill_md.rstrip().endswith("Steps here")


@pytest.mark.asyncio
async def test_missing_description_falls_back_to_trigger_condition_then_name() -> None:
    with_trigger = await _written_skill_md(_draft(description=None, content=None, trigger_condition="When files need converting"))
    bare = await _written_skill_md(_draft(description="  ", content=None))

    assert parse_skill_frontmatter(with_trigger, "convert-files").description == "When files need converting"
    assert parse_skill_frontmatter(bare, "convert-files").description == "convert-files"
