"""E2E Test for Unified Capability Discovery Gateway (bound skills path)."""

from __future__ import annotations

import os

import pytest
from myrm_agent_harness.agent.meta_tools.mount_policy import FileAccessMode
from myrm_agent_harness.agent.skill_agent import SkillAgent
from myrm_agent_harness.agent.streaming.types import AgentEventType
from myrm_agent_harness.agent.types import AgentRuntimeConfig
from myrm_agent_harness.backends.skills.types import SkillMetadata
from myrm_agent_harness.toolkits.llms.core.llm import create_litellm_model

from tests.api.agent.utils import _convert_litellm_model

_SKILL_NAME = "e2e_discover_dummy_skill"


class _StubSkillBackend:
    """Minimal SkillBackend stub for list_skills only."""

    def __init__(self, skills: list[SkillMetadata]) -> None:
        self._skills = skills

    async def list_skills(self) -> list[SkillMetadata]:
        return list(self._skills)

    async def load_skills(self, skill_ids: list[str]) -> list[SkillMetadata]:
        by_name = {skill.name: skill for skill in self._skills}
        return [by_name[skill_id] for skill_id in skill_ids if skill_id in by_name]

    async def get_skill_content(self, skill_name: str) -> str:
        return f"# {skill_name}\n"

    async def get_skill_resources(self, skill_name: str, path: str) -> bytes:
        return b""


def _sample_skill() -> SkillMetadata:
    return SkillMetadata(
        name=_SKILL_NAME,
        description="End-to-end discovery test skill for bound capability lookup.",
        model_invocable=True,
        available=True,
    )


def _skills_for_search_mount(*, featured: SkillMetadata | None = None) -> list[SkillMetadata]:
    """21 bound skills → hidden_count > 0 → skill_search_tool mounts (catalog_display SSOT)."""
    skills = [
        SkillMetadata(
            name=f"bound_skill_{index:02d}",
            description=f"Bound skill {index} for discover e2e",
            model_invocable=True,
            available=True,
        )
        for index in range(21)
    ]
    if featured is not None:
        featured_inline = SkillMetadata(
            name=featured.name,
            description=featured.description,
            model_invocable=featured.model_invocable,
            available=featured.available,
            always=True,
        )
        skills[0] = featured_inline
    return skills


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_discover_capability_e2e_real_model() -> None:
    """Real-model E2E: agent invokes skill_search_tool when hidden bound skills exist.

    skill_search_tool mounts only when ``hidden_skill_count > 0``
    (``sync_discover_capability_tool`` + ``should_mount_skill_search_tool``).
    """
    api_key = os.environ.get("BASIC_API_KEY", "").strip()
    if not api_key:
        pytest.skip(
            "BASIC_API_KEY not found in environment (see myrm-agent-server/.env.test)"
        )

    base_url = (os.environ.get("BASIC_BASE_URL") or "").strip() or None
    raw_model = (
        os.environ.get("DISCOVER_CAPABILITY_E2E_MODEL")
        or os.environ.get("BASIC_MODEL")
        or "gpt-4o-mini"
    ).strip()

    llm = create_litellm_model(
        model=_convert_litellm_model(raw_model),
        api_key=api_key,
        base_url=base_url,
        temperature=0,
    )

    agent = SkillAgent(
        llm=llm,
        skill_backend=_StubSkillBackend(_skills_for_search_mount(featured=_sample_skill())),
        file_access_mode=FileAccessMode.NONE,
        enable_shell_tools=False,
        enable_answer_tool=False,
        system_prompt=(
            "You are a test assistant. You MUST call skill_search_tool exactly once "
            'with query "*" to list bound skills. Do NOT call skill_select_tool or any other '
            "tool. After the tool returns, reply with the skill names you found."
        ),
        config=AgentRuntimeConfig(parallel_tool_calls=False),
    )

    tool_calls_made: list[str] = []
    message_chunks: list[str] = []

    async for event in agent.run(
        'Call skill_search_tool with query "*" and summarize bound skill names.',
        context={
            "session_id": "test_discover_e2e",
            "workspaces_storage_root": "/tmp/myrm_test_workspaces",
        },
    ):
        et = event.get("type")
        if et == AgentEventType.TASKS_STEPS.value:
            tn = event.get("tool_name")
            if tn:
                tool_calls_made.append(str(tn))
        elif et == AgentEventType.MESSAGE.value and isinstance(event.get("data"), str):
            message_chunks.append(event["data"])

    final_response = "".join(message_chunks).strip()

    if "skill_search_tool" not in tool_calls_made:
        pytest.skip(
            f"model did not invoke skill_search_tool (got {tool_calls_made!r}); "
            f"model={raw_model!r}; deterministic wiring covered in harness integration tests"
        )

    assert final_response, "Agent did not produce a final response"
    assert (
        _SKILL_NAME in final_response or _SKILL_NAME in " ".join(message_chunks).lower()
    )
