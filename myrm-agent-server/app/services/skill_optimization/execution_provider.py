"""Skill Execution Provider Implementation

Server layer SkillExecutionProvider: shadow tests plus EventLog-backed execution samples.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from myrm_agent_harness.agent.skills.optimization import EventLogAdapter, SkillExecutionSample
    from myrm_agent_harness.backends.skills.types import SkillMetadata

logger = logging.getLogger(__name__)


def _default_event_log_adapter() -> EventLogAdapter:
    from myrm_agent_harness.agent.event_log.backends.file_backend import FileEventLogBackend
    from myrm_agent_harness.agent.skills.optimization.event_adapter import EventLogAdapter

    from app.config.settings import get_settings

    settings = get_settings()
    log_dir = Path(settings.database.event_log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    backend = FileEventLogBackend(log_dir=log_dir, session_id="_skill_optimization_scan")
    return EventLogAdapter(backend)


class ServerSkillExecutionProvider:
    """Skill execution provider for optimization, shadow tests, and analytics."""

    def __init__(self, event_log_adapter: EventLogAdapter | None = None) -> None:
        self._event_log_adapter = event_log_adapter

    def _adapter(self) -> EventLogAdapter:
        if self._event_log_adapter is None:
            self._event_log_adapter = _default_event_log_adapter()
        return self._event_log_adapter

    async def _tool_name_aliases(self, skill_id: str) -> frozenset[str]:
        from app.core.skills.runtime_metadata import skill_to_runtime_metadata
        from app.core.skills.store.service import skills_service

        skill = await skills_service.get_skill(skill_id)
        if skill is None:
            return frozenset()
        meta = skill_to_runtime_metadata(skill)
        aliases = {meta.name, skill.name, skill.id}
        if skill.id != skill_id:
            aliases.add(skill_id)
        return frozenset(aliases)

    async def _catalog_tool_to_skill_id(self) -> dict[str, str]:
        from app.core.skills.runtime_metadata import skill_to_runtime_metadata
        from app.core.skills.store.service import skills_service

        mapping: dict[str, str] = {}
        for skill in await skills_service.get_user_available_skills():
            meta = skill_to_runtime_metadata(skill)
            mapping[meta.name] = skill.id
            mapping[skill.id] = skill.id
            mapping[skill.name] = skill.id
        return mapping

    async def get_skill_executions(
        self,
        skill_id: str,
        days: int = 7,
        session_id: str | None = None,
    ) -> list[SkillExecutionSample]:
        aliases = await self._tool_name_aliases(skill_id)
        return await self._adapter().get_skill_executions(
            skill_id,
            days,
            session_id,
            tool_name_aliases=aliases,
        )

    async def get_all_skill_ids(self) -> list[str]:
        adapter = self._adapter()
        tool_names = await adapter.collect_tool_names()
        catalog = await self._catalog_tool_to_skill_id()
        skill_ids = {catalog[name] for name in tool_names if name in catalog}
        return sorted(skill_ids)

    async def count_executions(
        self,
        skill_id: str,
        days: int = 7,
    ) -> int:
        return len(await self.get_skill_executions(skill_id, days))

    async def get_skill_metadata(self, skill_id: str) -> SkillMetadata | None:
        from app.core.skills.runtime_metadata import skill_to_runtime_metadata
        from app.core.skills.store.service import skills_service

        skill = await skills_service.get_skill(skill_id)
        if skill is None:
            return None
        return skill_to_runtime_metadata(skill)

    async def execute_skill_version(
        self,
        skill_id: str,
        version: int,
        inputs: dict[str, object],
        isolated_mode: bool = False,
    ) -> dict[str, object]:
        """Execute a specific skill version (shadow / A-B validation)."""
        logger.info("Executing skill %s version %s (isolated=%s)", skill_id, version, isolated_mode)

        from myrm_agent_harness.backends.skills.decorators.version_aware import forced_version_var

        from app.ai_agents.general_agent.agent import GeneralAgent
        from app.core.types import ModelConfig
        from app.services.agent.platform_config import load_platform_model_config

        token = forced_version_var.set(version)

        try:
            platform_model = await load_platform_model_config()

            temp_agent = GeneralAgent(
                model_cfg=ModelConfig(
                    model=platform_model.model,
                    api_key=platform_model.api_key,
                    base_url=platform_model.base_url,
                    api_keys=platform_model.api_keys,
                ),
                mcp_config=None,
                search_service_cfg=None,
                enable_web_search=False,
                skill_ids=[skill_id],
            )

            await temp_agent._init_agent(effective_chat_id="shadow_test")

            agent_impl = temp_agent.agent
            if agent_impl is None:
                raise ValueError("Agent failed to initialize for shadow test")

            tool = next((t for t in agent_impl.user_tools if t.name == skill_id), None)
            if not tool:
                raise ValueError(f"Tool {skill_id} not found in agent for shadow test")

            result = await tool.ainvoke(inputs)

            return {"status": "success", "result": result, "version": version}

        except Exception as e:
            logger.error("Execution failed for %s v%s: %s", skill_id, version, e)
            return {"status": "error", "error": str(e), "version": version}
        finally:
            forced_version_var.reset(token)


__all__ = ["ServerSkillExecutionProvider"]
