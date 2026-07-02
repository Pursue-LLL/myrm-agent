"""Database-backed implementation of AgentProfileBackend."""

import logging
from typing import cast

from myrm_agent_harness.backends.profiles.types import AgentProfile
from myrm_agent_harness.toolkits.memory.config import AgentMemoryPolicy
from sqlalchemy import select

from app.ai_agents.personality_templates import DEFAULT_PERSONALITY_STYLE
from app.core.memory.adapters.policy import memory_policy_from_dict, memory_policy_to_dict
from app.database.connection import get_session
from app.database.models import Agent
from app.services.agent.builtin_tool_ids import persist_enabled_builtin_tools

logger = logging.getLogger(__name__)


class DatabaseProfileBackend:
    """Database-backed profile store (async).

    Runtime contract matches call sites that expect database-backed CRUD;
    this is not a nominal `AgentProfileBackend` implementation because that
    protocol is synchronous while persistence here is async.

    Uses SQLAlchemy to store and retrieve agent profiles from the `agents` table.
    Provides data sovereignty and tight integration with the business layer database.
    """

    @staticmethod
    def _agent_to_profile(agent: Agent) -> AgentProfile:
        """Convert Agent DB model to AgentProfile dataclass."""
        return AgentProfile(
            id=agent.id,
            display_name=agent.name,
            description=agent.description,
            avatar=agent.avatar,
            model=agent.model_config.get("model") if agent.model_config else None,
            max_iterations=agent.max_iterations,
            system_prompt=agent.system_prompt,
            skills=agent.skill_ids,
            tools_allowed=agent.enabled_builtin_tools,
            memory_policy=memory_policy_from_dict(agent.memory_policy),
            metadata={
                "mcp_ids": agent.mcp_servers,
                "mcp_tool_selections": agent.mcp_tool_selections,
                "enabled_builtin_tools": agent.enabled_builtin_tools,
                "home_directory": agent.home_directory,
                "prompt_mode": agent.prompt_mode or "full",
                "personality_style": agent.personality_style or DEFAULT_PERSONALITY_STYLE,
                "security_overrides": agent.security_overrides,
                "subagent_ids": agent.subagent_ids,
                "workspace_policy": agent.workspace_policy,
                "engine_params": agent.engine_params,
                "model_selection_full": agent.model_selection,
            },
            built_in=agent.is_built_in or agent.is_public,
            created_at=agent.created_at,
            updated_at=agent.updated_at,
        )

    async def get_profile(self, agent_id: str) -> AgentProfile | None:
        """Get an agent profile by ID."""
        async with get_session() as db:
            result = await db.execute(select(Agent).where(Agent.id == agent_id))
            agent = result.scalar_one_or_none()

            if not agent:
                return None

            return self._agent_to_profile(agent)

    async def create_profile(self, profile: AgentProfile, home_directory: str | None = None) -> tuple[AgentProfile, str]:
        """Create a new agent profile."""
        async with get_session() as db:
            # Create new
            _ = "system"  # Default or require user_id in profile?

            # Check if agent with this ID already exists
            result = await db.execute(select(Agent).where(Agent.id == profile.id))
            existing_agent = result.scalar_one_or_none()

            if existing_agent:
                raise ValueError(f"Agent with ID {profile.id} already exists")

            meta = profile.metadata or {}
            full_model_selection = meta.pop("_model_selection_full", None)
            agent = Agent(
                id=profile.id,
                user_id="local",
                name=profile.display_name or "Unnamed Agent",
                description=profile.description or "",
                avatar=profile.avatar,
                home_directory=meta.get("home_directory"),
                model_config={"model": profile.model} if profile.model else {},
                model_selection=full_model_selection
                or ({"providerId": "auto", "model": profile.model} if profile.model else None),
                system_prompt=profile.system_prompt,
                memory_policy=memory_policy_to_dict(profile.memory_policy),
                max_iterations=profile.max_iterations,
                skill_ids=profile.skills or [],
                mcp_servers=meta.get("mcp_ids", []),
                mcp_tool_selections=meta.get("mcp_tool_selections"),
                subagent_ids=meta.get("subagent_ids", []),
                enabled_builtin_tools=persist_enabled_builtin_tools(
                    meta.get("enabled_builtin_tools", profile.tools_allowed)
                ),
                prompt_mode=meta.get("prompt_mode", "full"),
                personality_style=meta.get("personality_style", DEFAULT_PERSONALITY_STYLE),
                security_overrides=meta.get("security_overrides"),
                workspace_policy=meta.get("workspace_policy", "INHERIT_REQUESTER"),
                is_active=True,
                is_public=profile.built_in,
                is_built_in=profile.built_in,
            )
            db.add(agent)
            await db.commit()
        return profile, home_directory or ""

    async def update_profile(self, agent_id: str, updates: dict[str, object]) -> AgentProfile | None:
        """Update an existing agent profile."""
        async with get_session() as db:
            result = await db.execute(select(Agent).where(Agent.id == agent_id))
            agent = result.scalar_one_or_none()

            if not agent:
                return None

            # Update existing (narrow ``object`` values for ORM assignment)
            if "display_name" in updates:
                v = updates["display_name"]
                if isinstance(v, str):
                    agent.name = v
            if "description" in updates:
                v = updates["description"]
                if isinstance(v, str):
                    agent.description = v
            if "avatar" in updates:
                v = updates["avatar"]
                if v is None or isinstance(v, str):
                    agent.avatar = v
            if "model" in updates:
                v = updates["model"]
                if v is None or isinstance(v, str):
                    agent.model_config = {"model": v}
                    if "model_selection" in updates and isinstance(updates["model_selection"], dict):
                        agent.model_selection = updates["model_selection"]
                    else:
                        agent.model_selection = {"providerId": "auto", "model": v} if v else None
            if "system_prompt" in updates:
                v = updates["system_prompt"]
                if v is None or isinstance(v, str):
                    agent.system_prompt = v
            if "skills" in updates:
                v = updates["skills"]
                if isinstance(v, list):
                    agent.skill_ids = [str(x) for x in v]
            if "built_in" in updates:
                v = updates["built_in"]
                if isinstance(v, bool):
                    agent.is_public = v
                    agent.is_built_in = v
            if "max_iterations" in updates:
                v = updates["max_iterations"]
                if v is None or isinstance(v, int):
                    agent.max_iterations = v
            if "tools_allowed" in updates:
                v = updates["tools_allowed"]
                if isinstance(v, list):
                    agent.enabled_builtin_tools = persist_enabled_builtin_tools(v)
            if "memory_policy" in updates:
                agent.memory_policy = memory_policy_to_dict(cast(AgentMemoryPolicy | None, updates["memory_policy"]))
            if "workspace_policy" in updates:
                v = updates["workspace_policy"]
                if isinstance(v, str):
                    agent.workspace_policy = v

            if "metadata" in updates:
                meta_raw = updates["metadata"]
                if isinstance(meta_raw, dict):
                    metadata = cast(dict[str, object], meta_raw)
                    if "mcp_ids" in metadata and isinstance(metadata["mcp_ids"], list):
                        agent.mcp_servers = [str(x) for x in metadata["mcp_ids"]]
                    if "mcp_tool_selections" in metadata:
                        sel = metadata["mcp_tool_selections"]
                        agent.mcp_tool_selections = cast(dict[str, list[str]], sel) if isinstance(sel, dict) else None
                    if "enabled_builtin_tools" in metadata and isinstance(metadata["enabled_builtin_tools"], list):
                        agent.enabled_builtin_tools = persist_enabled_builtin_tools(
                            metadata["enabled_builtin_tools"]
                        )
                    if "home_directory" in metadata:
                        hd = metadata["home_directory"]
                        if hd is None or isinstance(hd, str):
                            agent.home_directory = hd
                    if "prompt_mode" in metadata:
                        pm = metadata["prompt_mode"]
                        if isinstance(pm, str):
                            agent.prompt_mode = pm
                    if "personality_style" in metadata:
                        ps = metadata["personality_style"]
                        if isinstance(ps, str):
                            agent.personality_style = ps
                    if "security_overrides" in metadata:
                        so = metadata["security_overrides"]
                        if so is None:
                            agent.security_overrides = None
                        elif isinstance(so, dict):
                            agent.security_overrides = cast(dict[str, object], so)
                    if "subagent_ids" in metadata and isinstance(metadata["subagent_ids"], list):
                        agent.subagent_ids = [str(x) for x in metadata["subagent_ids"]]
                    if "workspace_policy" in metadata:
                        wp = metadata["workspace_policy"]
                        if isinstance(wp, str):
                            agent.workspace_policy = wp
                    if "engine_params" in metadata:
                        ep = metadata["engine_params"]
                        if ep is None or isinstance(ep, dict):
                            agent.engine_params = ep

            await db.commit()
            await db.refresh(agent)

            return self._agent_to_profile(agent)

    async def delete_profile(self, agent_id: str) -> bool:
        """Delete an agent profile."""
        async with get_session() as db:
            result = await db.execute(select(Agent).where(Agent.id == agent_id))
            agent = result.scalar_one_or_none()

            if agent:
                await db.delete(agent)
                await db.commit()
                return True
            return False

    async def list_profiles(self) -> list[AgentProfile]:
        """List all agent profiles."""
        async with get_session() as db:
            result = await db.execute(select(Agent))
            agents = result.scalars().all()

            return [self._agent_to_profile(agent) for agent in agents]
