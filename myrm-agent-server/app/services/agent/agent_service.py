"""智能体服务（基于 UnitOfWork）

[INPUT]
Agent CRUD请求、agent_id、user_id

[OUTPUT]
AgentProfile 实例、AgentUpdateOutcome（含 snapshot_saved）、操作结果

[POS]
业务层Agent服务。
- 单机/沙箱模式，无多租户隔离（忽略 user_id）
- 所有额外字段存入 metadata
- 负责维护数据一致性（删除时级联清理渠道绑定、更新/删除时失效 IM 渠道的 agent overrides 缓存、CRUD 后异步热重载技能命令绑定）
"""

import asyncio
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

from myrm_agent_harness.backends.profiles.types import AgentProfile, CommandBinding
from myrm_agent_harness.toolkits.memory.config import AgentMemoryPolicy

from app.config.settings import settings
from app.core.memory.adapters.policy import memory_policy_from_dict
from app.database.dto import AgentCreate, AgentUpdate, CommandBindingConfig
from app.database.repositories.uow import UnitOfWork
from app.services.agent.profile_snapshot_service import (
    ProfileSnapshotService,
    has_mutable_diff,
)
from app.services.event.app_event_bus import AppEvent, AppEventType, get_event_bus

logger = logging.getLogger(__name__)

HIDDEN_SYSTEM_PROMPT = "⚠️ [Hidden for security]"


@dataclass(frozen=True)
class AgentUpdateOutcome:
    profile: AgentProfile
    snapshot_saved: bool


class _AgentRepositoryPort(Protocol):
    async def list_profiles(self) -> list[AgentProfile]: ...

    async def get_profile(self, agent_id: str) -> AgentProfile | None: ...

    async def create_profile(self, profile: AgentProfile) -> AgentProfile: ...

    async def update_profile(self, agent_id: str, updates: dict[str, object]) -> AgentProfile | None: ...

    async def delete_profile(self, agent_id: str) -> bool: ...


def _memory_policy_from_request(raw: object) -> AgentMemoryPolicy | None:
    if raw is None:
        return None
    if hasattr(raw, "model_dump"):
        dumped = raw.model_dump(mode="json", exclude_none=True)
        return memory_policy_from_dict(dumped)
    return None


def _command_bindings_from_request(
    raw: list[CommandBindingConfig] | None,
) -> list[CommandBinding] | None:
    """Convert DTO CommandBindingConfig list to harness CommandBinding list."""
    if not raw:
        return None
    return [
        CommandBinding(
            command_name=b.command_name,
            skill_id=b.skill_id,
            description=b.description,
            aliases=tuple(b.aliases),
        )
        for b in raw
    ] or None


def _invalidate_agent_profile_cache(agent_id: str) -> None:
    """Ensure profile-bound entry points see the newest agent contract immediately."""
    try:
        from app.services.agent.profile_resolver import get_agent_profile_resolver

        get_agent_profile_resolver().invalidate(agent_id)
    except Exception as e:
        logger.warning("Failed to invalidate AgentProfileResolver cache for '%s': %s", agent_id, e)


# 确保 harness 目录存在
os.makedirs(settings.database.harness_dir, exist_ok=True)
harness_db_path = str(Path(settings.database.harness_dir) / "agents_index.db")
harness_agents_dir = str(Path(settings.database.harness_dir) / "agents")


def _notify_agent_update(agent_id: str, action: str) -> None:
    """发送 Agent 更新事件"""
    try:
        bus = get_event_bus()
        bus.publish(
            AppEvent(
                event_type=AppEventType.AGENT_CONFIG_UPDATED,
                data={"agent_id": agent_id, "action": action},
            )
        )
    except Exception as e:
        logger.error(f"Failed to publish agent update event: {e}")


def _invalidate_channel_agent_cache(agent_id: str) -> None:
    """Invalidate shared resolver cache used by Web / IM / Cron entry points."""
    _invalidate_agent_profile_cache(agent_id)


def _finalize_profile_mutation(agent_id: str, action: str) -> None:
    _notify_agent_update(agent_id, action)
    _invalidate_agent_profile_cache(agent_id)
    _reload_command_bindings()


def _reload_command_bindings() -> None:
    """Schedule async reload of skill command bindings in the CommandRegistry.

    Called after agent create/update/delete when command_bindings may have changed.
    Uses asyncio.create_task to avoid blocking the current sync call path.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return

    from app.core.channel_bridge.setup import reload_skill_command_bindings

    loop.create_task(reload_skill_command_bindings())


class AgentService:
    """智能体服务类"""

    @staticmethod
    def _ar(uow: UnitOfWork) -> _AgentRepositoryPort:
        return cast(_AgentRepositoryPort, uow.agent_repo)

    @staticmethod
    async def get_agent_list(page: int = 1, page_size: int = 20) -> tuple[list[AgentProfile], int]:
        """获取智能体列表（支持分页）"""
        async with UnitOfWork() as uow:
            profiles = await AgentService._ar(uow).list_profiles()
            total = len(profiles)

            # 内存分页
            offset = (page - 1) * page_size
            paginated = profiles[offset : offset + page_size]

            return paginated, total

    @staticmethod
    async def get_agent_by_id(agent_id: str) -> AgentProfile | None:
        """根据 ID 获取智能体详情"""
        async with UnitOfWork() as uow:
            return await AgentService._ar(uow).get_profile(agent_id)

    @staticmethod
    async def get_agent_by_name(name: str) -> AgentProfile | None:
        """根据名称获取智能体（不区分大小写）"""
        async with UnitOfWork() as uow:
            profiles = await AgentService._ar(uow).list_profiles()
            for p in profiles:
                if p.display_name and p.display_name.lower() == name.lower():
                    return p
            return None

    @staticmethod
    async def resolve_agent(agent_id_or_name: str) -> AgentProfile | None:
        """按 ID 或名称解析智能体（ID 优先）"""
        agent = await AgentService.get_agent_by_id(agent_id_or_name)
        if agent:
            return agent
        return await AgentService.get_agent_by_name(agent_id_or_name)

    @staticmethod
    async def create_agent(agent_data: AgentCreate) -> AgentProfile:
        """创建智能体"""
        import uuid

        agent_id = str(uuid.uuid4())

        metadata: dict[str, object] = {
            "mcp_ids": agent_data.mcp_ids,
            "mcp_tool_selections": agent_data.mcp_tool_selections,
            "enabled_builtin_tools": agent_data.enabled_builtin_tools,
            "auto_restore_domains": list(agent_data.auto_restore_domains or []),
            "suggestion_prompts": agent_data.suggestion_prompts,
            "home_directory": agent_data.home_directory,
            "security_overrides": agent_data.security_overrides,
            "required_capabilities": agent_data.required_capabilities,
            "prompt_mode": agent_data.prompt_mode,
            "personality_style": agent_data.personality_style,
            "allow_discovery": agent_data.allow_discovery,
            "subagent_ids": agent_data.subagent_ids,
            "workspace_policy": agent_data.workspace_policy,
            "engine_params": agent_data.engine_params,
            "openapi_services": agent_data.openapi_services or [],
            "agent_type": agent_data.agent_type,
            "session_policy": (
                agent_data.session_policy.model_dump(mode="json")
                if agent_data.session_policy
                else None
            ),
            "notify_targets": agent_data.notify_targets,
            "tool_gateway_config": agent_data.tool_gateway_config.model_dump(mode="json") if getattr(agent_data, "tool_gateway_config", None) else None,
        }

        profile = AgentProfile(
            id=agent_id,
            display_name=agent_data.name,
            description=agent_data.description,
            avatar=agent_data.avatar_url,
            model=(agent_data.model_selection.model if agent_data.model_selection else None),
            max_iterations=agent_data.max_iterations,
            skills=agent_data.skill_ids,
            skill_configs=agent_data.skill_configs,
            tools_allowed=agent_data.enabled_builtin_tools,
            system_prompt=agent_data.system_prompt,
            memory_policy=_memory_policy_from_request(agent_data.memory_policy),
            command_bindings=_command_bindings_from_request(agent_data.command_bindings),
            metadata=metadata,
            built_in=agent_data.is_built_in,
        )

        if agent_data.model_selection:
            metadata["_model_selection_full"] = agent_data.model_selection.model_dump(by_alias=True, exclude_none=True)

        async with UnitOfWork() as uow:
            created_profile = await AgentService._ar(uow).create_profile(profile)

        _notify_agent_update(created_profile.id, "created")
        _invalidate_agent_profile_cache(created_profile.id)
        _reload_command_bindings()

        logger.info(f"✅ 创建智能体: {created_profile.id} (name={created_profile.display_name})")
        return created_profile

    @staticmethod
    async def update_agent(agent_id: str, agent_data: AgentUpdate) -> AgentUpdateOutcome | None:
        """更新智能体"""
        snapshot_saved = True
        async with UnitOfWork() as uow:
            existing = await AgentService._ar(uow).get_profile(agent_id)
            if not existing:
                return None

            updates: dict[str, object] = {}
            if agent_data.name is not None:
                updates["display_name"] = agent_data.name
            if agent_data.description is not None:
                updates["description"] = agent_data.description
            if agent_data.avatar_url is not None:
                updates["avatar"] = agent_data.avatar_url
            if agent_data.model_selection is not None:
                updates["model"] = agent_data.model_selection.model
                updates["model_selection"] = agent_data.model_selection.model_dump(by_alias=True, exclude_none=True)
            if agent_data.skill_ids is not None:
                updates["skills"] = agent_data.skill_ids
            if agent_data.skill_configs is not None:
                updates["skill_configs"] = agent_data.skill_configs
            if agent_data.enabled_builtin_tools is not None:
                updates["tools_allowed"] = agent_data.enabled_builtin_tools
            if agent_data.is_built_in is not None and not existing.built_in:
                updates["built_in"] = agent_data.is_built_in

            if agent_data.system_prompt is not None and agent_data.system_prompt != HIDDEN_SYSTEM_PROMPT:
                updates["system_prompt"] = agent_data.system_prompt
            if agent_data.max_iterations is not None:
                updates["max_iterations"] = agent_data.max_iterations
            if "memory_policy" in agent_data.model_fields_set:
                updates["memory_policy"] = _memory_policy_from_request(agent_data.memory_policy)
            if "workspace_policy" in agent_data.model_fields_set and agent_data.workspace_policy is not None:
                updates["workspace_policy"] = agent_data.workspace_policy

            # 更新 metadata
            new_metadata = dict(existing.metadata) if existing.metadata else {}
            if agent_data.mcp_ids is not None:
                new_metadata["mcp_ids"] = agent_data.mcp_ids
            if agent_data.mcp_tool_selections is not None:
                new_metadata["mcp_tool_selections"] = agent_data.mcp_tool_selections
            if agent_data.enabled_builtin_tools is not None:
                new_metadata["enabled_builtin_tools"] = agent_data.enabled_builtin_tools
            if "home_directory" in agent_data.model_fields_set:
                new_metadata["home_directory"] = agent_data.home_directory
            if agent_data.security_overrides is not None:
                new_metadata["security_overrides"] = agent_data.security_overrides
            if agent_data.prompt_mode is not None:
                new_metadata["prompt_mode"] = agent_data.prompt_mode
            if agent_data.personality_style is not None:
                new_metadata["personality_style"] = agent_data.personality_style
            if "allow_discovery" in agent_data.model_fields_set:
                new_metadata["allow_discovery"] = agent_data.allow_discovery
            if agent_data.subagent_ids is not None:
                new_metadata["subagent_ids"] = agent_data.subagent_ids
            if "workspace_policy" in agent_data.model_fields_set:
                new_metadata["workspace_policy"] = agent_data.workspace_policy
            if "engine_params" in agent_data.model_fields_set:
                new_metadata["engine_params"] = agent_data.engine_params
            if "auto_restore_domains" in agent_data.model_fields_set:
                new_metadata["auto_restore_domains"] = list(agent_data.auto_restore_domains or [])
            if "suggestion_prompts" in agent_data.model_fields_set:
                new_metadata["suggestion_prompts"] = agent_data.suggestion_prompts
            if "openapi_services" in agent_data.model_fields_set:
                new_metadata["openapi_services"] = agent_data.openapi_services or []
            if agent_data.agent_type is not None:
                new_metadata["agent_type"] = agent_data.agent_type
            if "session_policy" in agent_data.model_fields_set:
                new_metadata["session_policy"] = (
                    agent_data.session_policy.model_dump(mode="json")
                    if agent_data.session_policy
                    else None
                )
            if "notify_targets" in agent_data.model_fields_set:
                new_metadata["notify_targets"] = agent_data.notify_targets
            if "tool_gateway_config" in agent_data.model_fields_set:
                new_metadata["tool_gateway_config"] = (
                    agent_data.tool_gateway_config.model_dump(mode="json")
                    if getattr(agent_data, "tool_gateway_config", None)
                    else None
                )

            updates["metadata"] = new_metadata

            if "command_bindings" in agent_data.model_fields_set:
                updates["command_bindings"] = _command_bindings_from_request(agent_data.command_bindings)

            if not existing.built_in and has_mutable_diff(existing, updates):
                try:
                    saved_id = await ProfileSnapshotService.save_profile_snapshot(agent_id, reason="webui-update", uow=uow)
                    snapshot_saved = saved_id is not None
                except Exception as e:
                    snapshot_saved = False
                    logger.warning(
                        "Failed to save profile snapshot before WebUI update for '%s': %s",
                        agent_id,
                        e,
                    )

            updated_profile = await AgentService._ar(uow).update_profile(agent_id, updates)
            if updated_profile is None:
                return None

        _finalize_profile_mutation(agent_id, "updated")

        logger.info("Agent updated: %s", agent_id)
        return AgentUpdateOutcome(profile=updated_profile, snapshot_saved=snapshot_saved)

    @staticmethod
    async def delete_agent(agent_id: str) -> bool:
        """删除智能体 (包括级联清理渠道绑定)

        Raises:
            PermissionError: If the agent is a built-in agent (cannot be deleted).
        """
        async with UnitOfWork() as uow:
            existing = await AgentService._ar(uow).get_profile(agent_id)
            if existing and existing.built_in:
                raise PermissionError(f"Built-in agent '{agent_id}' cannot be deleted")
            success = await AgentService._ar(uow).delete_profile(agent_id)

        if success:
            # 级联清理所有该 Agent 的专属技能 (Orphan Skill GC)
            try:
                from myrm_agent_harness.agent.skills.evolution.db.store import SkillStore

                from app.config.settings import settings
                from pathlib import Path
                store = SkillStore(db_path=Path(settings.database.state_dir) / "skills.db")
                deleted_count = await store.delete_skills_by_agent(agent_id)
                if deleted_count > 0:
                    logger.info("Cascade deleted %d scoped skills for agent %s", deleted_count, agent_id)
                store.close()
            except Exception as e:
                logger.error("Failed to cascade delete skills for %s: %s", agent_id, e)

            # 级联清理所有该 Agent 的渠道绑定
            try:
                from app.core.channel_bridge.topic_config import SqlTopicManager

                manager = SqlTopicManager()
                await manager.remove_agent_from_all_bindings(agent_id)
            except Exception as e:
                logger.error(f"Failed to cascade delete bindings for agent {agent_id}: {e}")

            # 级联清理 Kanban 任务的 agent_id 引用
            try:
                from app.services.kanban import KanbanService

                kanban_svc = KanbanService.get_instance()
                cleared = await kanban_svc.clear_agent_references(agent_id)
                if cleared:
                    logger.info(
                        "Cleared agent_id on %d kanban tasks for agent %s",
                        cleared,
                        agent_id,
                    )
            except Exception as e:
                logger.error("Failed to clear kanban agent refs for %s: %s", agent_id, e)

            _finalize_profile_mutation(agent_id, "deleted")
            logger.info("Agent deleted: %s", agent_id)
        return success

    save_profile_snapshot = ProfileSnapshotService.save_profile_snapshot
    count_profile_snapshots = ProfileSnapshotService.count_profile_snapshots
    list_profile_snapshots = ProfileSnapshotService.list_profile_snapshots

    @staticmethod
    async def rollback_profile(agent_id: str) -> bool:
        ok = await ProfileSnapshotService.rollback_profile(agent_id)
        if ok:
            _finalize_profile_mutation(agent_id, "rollback")
        return ok

    @staticmethod
    async def rollback_profile_to_snapshot(agent_id: str, snapshot_id: str) -> bool:
        ok = await ProfileSnapshotService.rollback_profile_to_snapshot(agent_id, snapshot_id)
        if ok:
            _finalize_profile_mutation(agent_id, "rollback")
        return ok
