"""A fake installation for expert-export tests: experts, skill catalog, skill files and connectors.

[INPUT]
- app.core.skills.models::Skill (POS: catalog entry.)
- myrm_agent_harness.backends.profiles.types::AgentProfile (POS: stored expert.)

[OUTPUT]
- SKILL_MD: a minimal valid SKILL.md.
- ExportWorld: builder plus ``installed()`` that points the export closure at the fake installation.

[POS]
Test support only; the ``world`` fixture that activates it lives in tests/services/plugins/conftest.py.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from unittest.mock import AsyncMock, patch

from myrm_agent_harness.backends.profiles.types import AgentProfile
from myrm_agent_harness.toolkits.storage.types import SkillType

from app.core.skills.models import Skill

SKILL_MD = b"---\nname: report-writer\ndescription: Writes reports\nversion: 1.0.0\n---\n\n# Report writer\n"


class ExportWorld:
    """A fake installation the export closure reads (experts, skill catalog, skill files, connectors)."""

    def __init__(self) -> None:
        self.profiles: dict[str, AgentProfile] = {}
        self.skills: dict[str, Skill] = {}
        self.skill_files: dict[str, dict[str, bytes]] = {}
        self.servers: list[dict[str, object]] = []

    def expert(
        self,
        agent_id: str,
        name: str,
        *,
        skills: tuple[str, ...] = (),
        mcps: tuple[str, ...] = (),
        subagents: tuple[str, ...] = (),
        built_in: bool = False,
        model: str | None = None,
        max_iterations: int = 20,
        description: str | None = None,
        system_prompt: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> AgentProfile:
        profile = AgentProfile(
            id=agent_id,
            display_name=name,
            description=description if description is not None else f"{name} description",
            system_prompt=system_prompt if system_prompt is not None else f"You are {name}.",
            model=model,
            max_iterations=max_iterations,
            skills=list(skills),
            tools_allowed=["web_search"],
            built_in=built_in,
            metadata={"mcp_ids": list(mcps), "subagent_ids": list(subagents), **(metadata or {})},
        )
        self.profiles[agent_id] = profile
        return profile

    def custom_skill(
        self,
        skill_id: str,
        name: str,
        files: dict[str, bytes] | None = None,
        *,
        directory: str | None = None,
        source: str | None = None,
        version: str = "1.0.0",
    ) -> Skill:
        skill = Skill(
            id=skill_id,
            type=SkillType.LOCAL,
            name=name,
            description=f"{name} skill",
            storage_path=f"/home/user/skills/{directory or name}",
            version=version,
            installed_from={"source": source} if source else None,
        )
        self.skills[skill_id] = skill
        self.skill_files[skill_id] = {"SKILL.md": SKILL_MD} if files is None else files
        return skill

    def preset_skill(self, skill_id: str, name: str) -> Skill:
        skill = Skill(id=skill_id, type=SkillType.PREBUILT, name=name, description="", storage_path=f"/presets/{skill_id}")
        self.skills[skill_id] = skill
        return skill

    def server(self, **cfg: object) -> None:
        self.servers.append(cfg)

    async def _get_agent(self, agent_id: str) -> AgentProfile | None:
        return self.profiles.get(agent_id)

    async def _collect(self, _source: object, skill_id: str, **_kwargs: object) -> dict[str, bytes]:
        return dict(self.skill_files.get(skill_id, {}))

    @contextmanager
    def installed(self) -> Iterator[ExportWorld]:
        """Point the export closure at this installation for the duration of the block."""
        replacements: dict[str, object] = {
            "app.services.agent.agent_service.AgentService.get_agent_by_id": self._get_agent,
            "app.core.skills.store.service.skills_service.list_skills": AsyncMock(
                side_effect=lambda *_args, **_kwargs: list(self.skills.values())
            ),
            "app.core.skills.packaging.collect.collect_skill_files": self._collect,
            "app.services.plugins._mcp_persist._load_persisted_mcp_configs": AsyncMock(return_value=self.servers),
        }
        with ExitStack() as stack:
            for target, replacement in replacements.items():
                stack.enter_context(patch(target, replacement))
            yield self
