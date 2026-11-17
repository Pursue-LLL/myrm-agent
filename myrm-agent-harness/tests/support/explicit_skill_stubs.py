"""A SkillBackend stub, a SkillMetadata builder and a SkillAgent shell for the explicit-skill-injection tests.

[INPUT]
- myrm_agent_harness.agent.skill_agent::SkillAgent (POS: the agent whose preload expands a [use skill] tag)
- myrm_agent_harness.backends.skills.types::SkillMetadata, SkillTrust (POS: the skill record and its trust level)

[OUTPUT]
- StubSkillBackend: a SkillBackend that returns the SKILL.md text and resource names a test hands it, and raises
  FileNotFoundError for any other skill
- make_skill_metadata: a SkillMetadata with a storage id, an optional storage path, a trust level and the
  user-invocable flag
- make_preload_agent: a SkillAgent shell that holds only what the preload reads, whose backend lists the given skills

[POS]
Pytest-only helper shared by the explicit-skill-injection tests, so a test states the skills and SOPs it needs and not
how the agent and its backend are wired.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from myrm_agent_harness.agent.skill_agent import SkillAgent
from myrm_agent_harness.backends.skills.types import SkillMetadata, SkillTrust


@dataclass
class StubSkillBackend:
    """Minimal stub satisfying SkillBackend protocol for testing."""

    content_map: dict[str, str] = field(default_factory=dict)
    resource_map: dict[str, list[str]] = field(default_factory=dict)

    async def list_skills(self) -> list[SkillMetadata]:
        return []

    async def load_skills(self, ids: list[str]) -> list[SkillMetadata]:
        return []

    async def get_skill_content(self, skill_id: str) -> str:
        if skill_id in self.content_map:
            return self.content_map[skill_id]
        raise FileNotFoundError(f"Skill {skill_id} not found")

    async def get_skill_resources(self, skill_id: str, path: str) -> bytes:
        raise NotImplementedError

    async def list_skill_resources(self, skill_id: str) -> list[str]:
        return list(self.resource_map.get(skill_id, []))


def make_skill_metadata(
    name: str = "test_skill",
    storage_skill_id: str | None = "test_skill",
    storage_path: str | None = None,
    trust: SkillTrust = SkillTrust.TRUSTED,
    user_invocable: bool = True,
) -> SkillMetadata:
    return SkillMetadata(
        name=name,
        description=f"Test skill: {name}",
        storage_skill_id=storage_skill_id,
        storage_path=storage_path,
        trust=trust,
        user_invocable=user_invocable,
    )


def make_preload_agent(
    skills: list[SkillMetadata] | None = None,
    backend: StubSkillBackend | None = None,
) -> SkillAgent:
    """Create a minimal SkillAgent for testing preload logic."""
    agent = SkillAgent.__new__(SkillAgent)
    agent.skill_backend = backend
    agent._desired_skill_ids = None
    agent._trusted_skill_ids = frozenset()

    if skills is not None and backend is not None:

        async def _patched_list() -> list[SkillMetadata]:
            return skills

        backend.list_skills = _patched_list  # type: ignore[method-assign]

    return agent
