"""Agent profile snapshot persistence and rollback.

[INPUT]
database.repositories.uow::UnitOfWork (POS: 事务单元工作)
database.models.agent::AgentProfileSnapshot (POS: Agent 配置快照 ORM)

[OUTPUT]
ProfileSnapshotService: save（返回 snapshot id）/ list / count / rollback agent profile snapshots
has_mutable_diff: WebUI mutable 字段 diff 检测

[POS]
WebUI 配置安全网。在 mutable 字段变更前自动快照，支持撤销与时光机回滚。
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING, Protocol, cast

from myrm_agent_harness.backends.profiles.types import AgentProfile, CommandBinding
from myrm_agent_harness.toolkits.memory.config import AgentMemoryPolicy

from app.core.memory.adapters.policy import (
    memory_policy_from_dict,
    memory_policy_to_dict,
)
from app.database.dto import CommandBindingConfig
from app.database.repositories.uow import UnitOfWork

if TYPE_CHECKING:
    from app.database.models.agent import AgentProfileSnapshot

logger = logging.getLogger(__name__)

_SNAPSHOT_RETENTION = 10


class _AgentRepositoryPort(Protocol):
    async def get_profile(self, agent_id: str) -> AgentProfile | None: ...

    async def update_profile(self, agent_id: str, updates: dict[str, object]) -> AgentProfile | None: ...


def _repo(uow: UnitOfWork) -> _AgentRepositoryPort:
    return cast(_AgentRepositoryPort, uow.agent_repo)


def _normalize_str_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x) for x in value]
    return []


def _command_bindings_from_request(
    raw: list[CommandBindingConfig] | None,
) -> list[CommandBinding] | None:
    if not raw:
        return None
    return [
        CommandBinding(
            command_name=b.command_name,
            skill_ids=tuple(b.skill_ids),
            description=b.description,
            aliases=tuple(b.aliases),
            instruction=b.instruction,
        )
        for b in raw
    ] or None


def mutable_snapshot_data(profile: AgentProfile) -> dict[str, object]:
    metadata = profile.metadata or {}
    enabled_tools = profile.tools_allowed
    if enabled_tools is None:
        enabled_tools = _normalize_str_list(metadata.get("enabled_builtin_tools"))
    else:
        enabled_tools = _normalize_str_list(enabled_tools)

    command_bindings_raw: list[dict[str, object]] | None = None
    if profile.command_bindings:
        command_bindings_raw = [
            {
                "command_name": b.command_name,
                "skill_ids": list(b.skill_ids),
                "description": b.description,
                "aliases": list(b.aliases),
                "instruction": b.instruction,
            }
            for b in profile.command_bindings
        ]

    model_selection = metadata.get("_model_selection_full")
    if model_selection is None:
        model_selection = metadata.get("model_selection_full")

    raw_auto_restore = metadata.get("auto_restore_domains")
    auto_restore_domains: list[str] = []
    if isinstance(raw_auto_restore, list):
        auto_restore_domains = [str(x) for x in raw_auto_restore]

    raw_openapi = metadata.get("openapi_services", [])
    openapi_services = [item for item in raw_openapi if isinstance(item, dict)] if isinstance(raw_openapi, list) else []

    return {
        "display_name": profile.display_name,
        "description": profile.description,
        "system_prompt": profile.system_prompt,
        "personality_style": metadata.get("personality_style"),
        "model": profile.model,
        "model_selection": model_selection,
        "skill_ids": _normalize_str_list(profile.skills),
        "skill_configs": profile.skill_configs,
        "mcp_ids": _normalize_str_list(metadata.get("mcp_ids")),
        "mcp_tool_selections": metadata.get("mcp_tool_selections"),
        "enabled_builtin_tools": list(enabled_tools),
        "subagent_ids": _normalize_str_list(metadata.get("subagent_ids")),
        "security_overrides": metadata.get("security_overrides"),
        "max_iterations": profile.max_iterations,
        "workspace_policy": metadata.get("workspace_policy"),
        "memory_policy": memory_policy_to_dict(profile.memory_policy),
        "engine_params": metadata.get("engine_params"),
        "auto_restore_domains": auto_restore_domains,
        "openapi_services": openapi_services,
        "command_bindings": command_bindings_raw,
    }


def project_mutable_after_update(existing: AgentProfile, updates: dict[str, object]) -> dict[str, object]:
    projected = mutable_snapshot_data(existing)
    if "display_name" in updates:
        projected["display_name"] = updates["display_name"]
    if "description" in updates:
        projected["description"] = updates["description"]
    if "system_prompt" in updates:
        projected["system_prompt"] = updates["system_prompt"]
    if "model" in updates:
        projected["model"] = updates["model"]
    if "model_selection" in updates:
        projected["model_selection"] = updates["model_selection"]
    if "skills" in updates:
        projected["skill_ids"] = _normalize_str_list(updates["skills"])
    if "skill_configs" in updates:
        projected["skill_configs"] = updates["skill_configs"]
    if "max_iterations" in updates:
        projected["max_iterations"] = updates["max_iterations"]
    if "workspace_policy" in updates:
        projected["workspace_policy"] = updates["workspace_policy"]
    if "memory_policy" in updates:
        projected["memory_policy"] = memory_policy_to_dict(cast(AgentMemoryPolicy | None, updates["memory_policy"]))
    if "command_bindings" in updates:
        raw_bindings = updates["command_bindings"]
        if raw_bindings is None:
            projected["command_bindings"] = None
        elif isinstance(raw_bindings, list):
            projected["command_bindings"] = [
                (
                    {
                        "command_name": b.command_name,
                        "skill_ids": list(b.skill_ids),
                        "description": b.description,
                        "aliases": list(b.aliases),
                        "instruction": b.instruction,
                    }
                    if isinstance(b, CommandBinding)
                    else b
                )
                for b in raw_bindings
            ]
    if "tools_allowed" in updates:
        projected["enabled_builtin_tools"] = _normalize_str_list(updates["tools_allowed"])
    metadata_update = updates.get("metadata")
    if isinstance(metadata_update, dict):
        for key in (
            "personality_style",
            "mcp_ids",
            "mcp_tool_selections",
            "enabled_builtin_tools",
            "subagent_ids",
            "security_overrides",
            "engine_params",
            "auto_restore_domains",
            "openapi_services",
            "workspace_policy",
        ):
            if key in metadata_update:
                if key in {"mcp_ids", "subagent_ids", "enabled_builtin_tools"}:
                    projected[key] = _normalize_str_list(metadata_update[key])
                else:
                    projected[key] = metadata_update[key]
    return projected


def has_mutable_diff(existing: AgentProfile, updates: dict[str, object]) -> bool:
    return mutable_snapshot_data(existing) != project_mutable_after_update(existing, updates)


def _command_bindings_from_snapshot(raw: object) -> list[CommandBinding] | None:
    if raw is None or not isinstance(raw, list):
        return None
    configs: list[CommandBindingConfig] = []
    for item in raw:
        if isinstance(item, dict):
            configs.append(CommandBindingConfig.model_validate(item))
    return _command_bindings_from_request(configs)


def updates_from_snapshot_data(agent: AgentProfile, data: dict[str, object]) -> dict[str, object]:
    updates: dict[str, object] = {
        "display_name": data.get("display_name"),
        "description": data.get("description"),
        "system_prompt": data.get("system_prompt"),
        "model": data.get("model"),
        "skills": data.get("skill_ids", []),
        "skill_configs": data.get("skill_configs"),
        "max_iterations": data.get("max_iterations"),
    }
    if "workspace_policy" in data:
        updates["workspace_policy"] = data.get("workspace_policy")
    if "memory_policy" in data:
        raw_policy = data.get("memory_policy")
        updates["memory_policy"] = (
            memory_policy_from_dict(cast(dict[str, object], raw_policy)) if isinstance(raw_policy, dict) else None
        )
    if "command_bindings" in data:
        updates["command_bindings"] = _command_bindings_from_snapshot(data.get("command_bindings"))

    model_selection = data.get("model_selection")
    if isinstance(model_selection, dict):
        updates["model_selection"] = model_selection

    new_metadata = dict(agent.metadata) if agent.metadata else {}
    for key in (
        "personality_style",
        "mcp_ids",
        "mcp_tool_selections",
        "enabled_builtin_tools",
        "subagent_ids",
        "security_overrides",
        "engine_params",
        "auto_restore_domains",
        "openapi_services",
        "workspace_policy",
    ):
        if key in data:
            new_metadata[key] = data[key]
    if isinstance(model_selection, dict):
        new_metadata["_model_selection_full"] = model_selection
    updates["metadata"] = new_metadata
    return updates


class ProfileSnapshotService:
    @staticmethod
    async def save_profile_snapshot(agent_id: str, reason: str = "", uow: UnitOfWork | None = None) -> str | None:
        from datetime import datetime, timezone

        from sqlalchemy import delete, select

        from app.database.models.agent import AgentProfileSnapshot

        async def _execute_save(uow_instance: UnitOfWork) -> str | None:
            profile = await _repo(uow_instance).get_profile(agent_id)
            if not profile:
                return None

            snapshot_id = str(uuid.uuid4()).replace("-", "")
            snapshot = AgentProfileSnapshot(
                id=snapshot_id,
                agent_id=agent_id,
                snapshot_data=mutable_snapshot_data(profile),
                reason=reason,
                created_at=datetime.now(timezone.utc),
            )
            uow_instance.session.add(snapshot)

            stmt = (
                select(AgentProfileSnapshot.id)
                .where(AgentProfileSnapshot.agent_id == agent_id)
                .order_by(AgentProfileSnapshot.created_at.desc())
                .offset(_SNAPSHOT_RETENTION)
            )
            result = await uow_instance.session.execute(stmt)
            ids_to_delete = result.scalars().all()
            if ids_to_delete:
                del_stmt = delete(AgentProfileSnapshot).where(AgentProfileSnapshot.id.in_(ids_to_delete))
                await uow_instance.session.execute(del_stmt)

            return snapshot_id

        if uow is not None:
            return await _execute_save(uow)

        async with UnitOfWork() as new_uow:
            return await _execute_save(new_uow)

    @staticmethod
    async def count_profile_snapshots(agent_id: str) -> int:
        from sqlalchemy import func, select

        from app.database.models.agent import AgentProfileSnapshot

        async with UnitOfWork() as uow:
            stmt = select(func.count()).select_from(AgentProfileSnapshot).where(AgentProfileSnapshot.agent_id == agent_id)
            result = await uow.session.execute(stmt)
            return int(result.scalar_one())

    @staticmethod
    async def list_profile_snapshots(agent_id: str, limit: int = _SNAPSHOT_RETENTION) -> list[AgentProfileSnapshot]:
        from sqlalchemy import select

        from app.database.models.agent import AgentProfileSnapshot

        async with UnitOfWork() as uow:
            stmt = (
                select(AgentProfileSnapshot)
                .where(AgentProfileSnapshot.agent_id == agent_id)
                .order_by(
                    AgentProfileSnapshot.created_at.desc(),
                    AgentProfileSnapshot.id.desc(),
                )
                .limit(limit)
            )
            result = await uow.session.execute(stmt)
            return list(result.scalars().all())

    @staticmethod
    async def rollback_profile(agent_id: str) -> bool:
        from sqlalchemy import select

        from app.database.models.agent import AgentProfileSnapshot

        async with UnitOfWork() as uow:
            stmt = (
                select(AgentProfileSnapshot)
                .where(AgentProfileSnapshot.agent_id == agent_id)
                .order_by(AgentProfileSnapshot.created_at.desc())
                .limit(1)
            )
            result = await uow.session.execute(stmt)
            snapshot = result.scalars().first()
            if not snapshot:
                return False

        return await ProfileSnapshotService._restore_record(agent_id, snapshot, pre_rollback=True)

    @staticmethod
    async def rollback_profile_to_snapshot(agent_id: str, snapshot_id: str) -> bool:
        from sqlalchemy import select

        from app.database.models.agent import AgentProfileSnapshot

        pre_rollback_id = await ProfileSnapshotService.save_profile_snapshot(agent_id, reason="pre-rollback")
        if pre_rollback_id is None:
            return False

        async with UnitOfWork() as uow:
            stmt = select(AgentProfileSnapshot).where(
                AgentProfileSnapshot.id == snapshot_id,
                AgentProfileSnapshot.agent_id == agent_id,
            )
            result = await uow.session.execute(stmt)
            snapshot = result.scalars().first()
            if not snapshot:
                return False

            agent = await _repo(uow).get_profile(agent_id)
            if not agent:
                return False

            updates = updates_from_snapshot_data(agent, snapshot.snapshot_data)
            await _repo(uow).update_profile(agent_id, updates)

            await uow.commit()

        return True

    @staticmethod
    async def _restore_record(agent_id: str, snapshot: AgentProfileSnapshot, *, pre_rollback: bool) -> bool:
        if pre_rollback:
            await ProfileSnapshotService.save_profile_snapshot(agent_id, reason="pre-rollback")

        async with UnitOfWork() as uow:
            agent = await _repo(uow).get_profile(agent_id)
            if not agent:
                return False

            updates = updates_from_snapshot_data(agent, snapshot.snapshot_data)
            await _repo(uow).update_profile(agent_id, updates)
            await uow.commit()

        return True
