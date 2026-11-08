"""The skill loader tells the model how to call a skill script, and the way it tells is the way the executor accepts."""

from __future__ import annotations

import re
from unittest.mock import AsyncMock

from myrm_agent_harness.agent.meta_tools.skills.select.skill_document_loader import get_skill_document
from myrm_agent_harness.agent.skills.runtime.skill_invocation import (
    plain_skill_call,
    settings_withheld_note,
    skill_call_notice,
)
from myrm_agent_harness.backends.skills.types import SkillMetadata

BODY = "---\nname: demo\ndescription: d\n---\n# Demo\n\nRun the script.\n"


def _stored(storage_path: str | None = "/skills/demo") -> SkillMetadata:
    return SkillMetadata(name="demo", description="d", storage_skill_id="id-1", storage_path=storage_path)


def _example_calls(text: str) -> list[str]:
    return re.findall(r"`(python3 [^`]+)`", text)


async def test_a_stored_skill_document_opens_with_the_calling_convention() -> None:
    backend = AsyncMock()
    backend.get_skill_content.return_value = BODY

    document = await get_skill_document(_stored(), backend)

    assert document.startswith(f"# Demo\n\n{skill_call_notice('demo')}")
    assert document.rstrip().endswith("Run the script.")


async def test_a_skill_without_a_storage_path_gets_no_convention() -> None:
    backend = AsyncMock()
    backend.get_skill_content.return_value = BODY

    document = await get_skill_document(_stored(storage_path=None), backend)

    assert "Script calls" not in document


def test_the_example_the_model_is_given_is_a_plain_call_of_that_skill() -> None:
    examples = _example_calls(skill_call_notice("demo")) + _example_calls(settings_withheld_note("demo"))

    assert len(examples) == 2
    assert all(plain_skill_call(example) == "demo" for example in examples)
