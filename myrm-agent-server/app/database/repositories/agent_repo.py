"""Agent Repository — domain-driven data access layer for Agent entities.

[INPUT]
- app.database.models::Agent (POS: Agent ORM 模型)
- myrm_agent_harness.backends.profiles.types::AgentProfile (POS: Agent Profile 数据类型定义)
- app.core.memory.adapters.policy (POS: 记忆策略序列化/反序列化)

[OUTPUT]
- AgentRepository: Agent 领域数据仓储，提供 CRUD、ORM→AgentProfile 转换、历史快照（`snapshot_data` 含 `auto_restore_domains`）

[POS]
领域数据仓储层。负责 Agent 的 SQLAlchemy 交互，隔离服务层与数据库结构耦合。
所有写入 `Agent.enabled_builtin_tools` 的路径均经 `builtin_tool_ids.persist_enabled_builtin_tools` 校验。
"""

import uuid
from typing import cast

from myrm_agent_harness.backends.profiles.types import AgentProfile, CommandBinding
from myrm_agent_harness.toolkits.memory.config import AgentMemoryPolicy
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_agents.personality_templates import DEFAULT_PERSONALITY_STYLE
from app.core.memory.adapters.policy import (
    memory_policy_from_dict,
    memory_policy_to_dict,
)
from app.database.models import Agent
from app.services.agent.builtin_tool_ids import persist_enabled_builtin_tools


class AgentRepository:
    """
    Agent 领域的专有仓储类（Repository）。
    负责所有的 SQLAlchemy DB 交互，隔离上层服务（Service）与底层数据库结构的耦合。
    并负责将底层 Agent 模型转换为业务层的 AgentProfile 数据类。
    """

    @staticmethod
    def _agent_to_profile(agent: Agent) -> AgentProfile:
        """Convert Agent DB model to AgentProfile dataclass."""
        bindings: list[CommandBinding] | None = None
        if agent.command_bindings:
            bindings = [
                CommandBinding(
                    command_name=b["command_name"],
                    skill_ids=tuple(b["skill_ids"]) if "skill_ids" in b else (b["skill_id"],) if "skill_id" in b else (),
                    description=b.get("description", ""),
                    aliases=tuple(b.get("aliases", ())),
                    instruction=b.get("instruction", ""),
                )
                for b in agent.command_bindings
                if isinstance(b, dict) and "command_name" in b and ("skill_ids" in b or "skill_id" in b)
            ]
            if not bindings:
                bindings = None

        # Decrypt tool_gateway_config.auth_token if present
        gateway_config = agent.tool_gateway_config
        if gateway_config and isinstance(gateway_config, dict) and gateway_config.get("auth_token"):
            try:
                from myrm_agent_harness.utils.crypto.config_crypto import ConfigCrypto

                from app.core.security.master_key import MasterKeyProvider

                master_key = MasterKeyProvider.get_master_key()
                derived_key = ConfigCrypto.derive_key(master_key)

                encrypted_token = gateway_config["auth_token"]
                # Try to decrypt. If it fails, it might be plaintext (legacy)
                try:
                    decrypted = ConfigCrypto.decrypt_value(encrypted_token, derived_key)
                    gateway_config["auth_token"] = str(decrypted["value"])
                except Exception:
                    # Fallback to plaintext if decryption fails (legacy data)
                    pass
            except Exception as e:
                import logging

                logging.getLogger(__name__).warning(f"Failed to initialize crypto for gateway auth_token: {e}")

        return AgentProfile(
            id=agent.id,
            display_name=agent.name,
            description=agent.description,
            avatar=agent.avatar,
            model=agent.model_config.get("model") if agent.model_config else None,
            max_iterations=agent.max_iterations,
            system_prompt=agent.system_prompt,
            skills=agent.skill_ids,
            skill_configs=agent.skill_configs,
            tools_allowed=agent.enabled_builtin_tools,
            memory_policy=memory_policy_from_dict(agent.memory_policy),
            command_bindings=bindings,
            metadata={
                "mcp_ids": agent.mcp_servers,
                "mcp_tool_selections": agent.mcp_tool_selections,
                "enabled_builtin_tools": agent.enabled_builtin_tools,
                "auto_restore_domains": agent.auto_restore_domains or [],
                "suggestion_prompts": agent.suggestion_prompts,
                "home_directory": agent.home_directory,
                "prompt_mode": agent.prompt_mode or "full",
                "personality_style": agent.personality_style or DEFAULT_PERSONALITY_STYLE,
                "security_overrides": agent.security_overrides,
                "subagent_ids": agent.subagent_ids,
                "workspace_policy": agent.workspace_policy,
                "engine_params": agent.engine_params,
                "openapi_services": agent.openapi_services or [],
                "model_selection_full": agent.model_selection,
                "agent_type": agent.agent_type or "individual",
                "session_policy": agent.session_policy,
                "notify_targets": agent.notify_targets,
                "tool_gateway_config": agent.tool_gateway_config,
                "mounted_skill_ids": agent.mounted_skill_ids,
                "browser_source": agent.browser_source,
                "dialog_policy": agent.dialog_policy,
                "session_recording": agent.session_recording,
                "cron_post_run_verify": bool(getattr(agent, "cron_post_run_verify", False)),
            },
            built_in=agent.is_built_in or agent.is_public,
            created_at=agent.created_at,
            updated_at=agent.updated_at,
        )

    @staticmethod
    async def get_profile(db: AsyncSession, agent_id: str) -> AgentProfile | None:
        result = await db.execute(select(Agent).where(Agent.id == agent_id))
        agent = result.scalar_one_or_none()
        if not agent:
            return None
        return AgentRepository._agent_to_profile(agent)

    @staticmethod
    async def list_profiles(db: AsyncSession) -> list[AgentProfile]:
        result = await db.execute(select(Agent))
        agents = result.scalars().all()
        return [AgentRepository._agent_to_profile(agent) for agent in agents]

    @staticmethod
    async def create_profile(
        db: AsyncSession,
        profile: AgentProfile,
        *,
        cron_post_run_verify: bool = False,
    ) -> AgentProfile:
        # Check if agent with this ID already exists
        result = await db.execute(select(Agent).where(Agent.id == profile.id))
        existing_agent = result.scalar_one_or_none()
        if existing_agent:
            raise ValueError(f"Agent with ID {profile.id} already exists")

        meta = profile.metadata or {}

        # Encrypt tool_gateway_config.auth_token if present
        gateway_config = meta.get("tool_gateway_config")
        if gateway_config and isinstance(gateway_config, dict) and gateway_config.get("auth_token"):
            try:
                from myrm_agent_harness.utils.crypto.config_crypto import ConfigCrypto

                from app.core.security.master_key import MasterKeyProvider

                master_key = MasterKeyProvider.get_master_key()
                derived_key = ConfigCrypto.derive_key(master_key)

                # Encrypt the token and replace it in the dict
                raw_token = gateway_config["auth_token"]
                encrypted_token = ConfigCrypto.encrypt_value({"value": raw_token}, derived_key)
                gateway_config["auth_token"] = encrypted_token
            except Exception as e:
                import logging

                logging.getLogger(__name__).error(f"Failed to encrypt gateway auth_token: {e}")
                # We should probably fail hard here to prevent plaintext saving, but for safety we just remove it
                # if encryption fails, to avoid leaking.
                gateway_config.pop("auth_token", None)

        full_model_selection = meta.pop("_model_selection_full", None)
        raw_auto = meta.get("auto_restore_domains")
        auto_restore_val: list[str] | None = [str(x) for x in raw_auto] if isinstance(raw_auto, list) else None
        agent = Agent(
            id=profile.id,
            name=profile.display_name or "Unnamed Agent",
            description=profile.description or "",
            avatar=profile.avatar,
            home_directory=meta.get("home_directory"),
            agent_type=str(meta.get("agent_type", "individual")),
            model_config={"model": profile.model} if profile.model else {},
            model_selection=full_model_selection or ({"providerId": "auto", "model": profile.model} if profile.model else None),
            system_prompt=profile.system_prompt,
            memory_policy=memory_policy_to_dict(profile.memory_policy),
            max_iterations=profile.max_iterations,
            skill_ids=profile.skills or [],
            skill_configs=profile.skill_configs,
            mcp_servers=meta.get("mcp_ids", []),
            mcp_tool_selections=meta.get("mcp_tool_selections"),
            subagent_ids=meta.get("subagent_ids", []),
            enabled_builtin_tools=persist_enabled_builtin_tools(
                meta.get("enabled_builtin_tools", profile.tools_allowed)
            ),
            browser_source=meta.get("browser_source"),
            dialog_policy=meta.get("dialog_policy"),
            session_recording=meta.get("session_recording"),
            auto_restore_domains=auto_restore_val,
            security_overrides=meta.get("security_overrides"),
            engine_params=meta.get("engine_params"),
            suggestion_prompts=meta.get("suggestion_prompts"),
            openapi_services=meta.get("openapi_services") or None,
            prompt_mode=str(meta.get("prompt_mode", "full")),
            personality_style=meta.get("personality_style", DEFAULT_PERSONALITY_STYLE),
            workspace_policy=str(meta.get("workspace_policy", "INHERIT_REQUESTER")),
            session_policy=meta.get("session_policy"),
            notify_targets=meta.get("notify_targets"),
            tool_gateway_config=meta.get("tool_gateway_config"),
            cron_post_run_verify=cron_post_run_verify,
            mounted_skill_ids=meta.get("mounted_skill_ids", []),
            command_bindings=(
                [
                    {
                        "command_name": b.command_name,
                        "skill_ids": list(b.skill_ids),
                        "description": b.description,
                        "aliases": list(b.aliases),
                        "instruction": b.instruction,
                    }
                    for b in profile.command_bindings
                ]
                if profile.command_bindings
                else None
            ),
            is_active=True,
            is_public=profile.built_in,
            is_built_in=profile.built_in,
            version=1,
        )
        db.add(agent)

        from app.database.models.agent_history import AgentProfileHistory

        history_record = AgentProfileHistory(
            id=uuid.uuid4().hex,
            agent_id=agent.id,
            version=1,
            name=agent.name,
            description=agent.description,
            system_prompt=agent.system_prompt,
            personality_style=agent.personality_style,
            snapshot_data={
                "model_config": agent.model_config,
                "model_selection": agent.model_selection,
                "skill_ids": agent.skill_ids,
                "mcp_servers": agent.mcp_servers,
                "enabled_builtin_tools": agent.enabled_builtin_tools,
                "auto_restore_domains": agent.auto_restore_domains or [],
            },
        )
        db.add(history_record)

        await db.flush()
        await db.refresh(agent)
        return AgentRepository._agent_to_profile(agent)

    @staticmethod
    async def update_profile(db: AsyncSession, agent_id: str, updates: dict[str, object]) -> AgentProfile | None:
        result = await db.execute(select(Agent).where(Agent.id == agent_id))
        agent = result.scalar_one_or_none()
        if not agent:
            return None

        if "display_name" in updates:
            agent.name = cast(str, updates["display_name"])
        if "description" in updates:
            agent.description = cast(str, updates["description"])
        if "avatar" in updates:
            agent.avatar = cast(str | None, updates["avatar"])
        if "model" in updates:
            model = cast(str, updates["model"])
            agent.model_config = {"model": model}
            if "model_selection" in updates and isinstance(updates["model_selection"], dict):
                agent.model_selection = updates["model_selection"]
            else:
                agent.model_selection = {"providerId": "auto", "model": model} if model else None
        if "system_prompt" in updates:
            agent.system_prompt = cast(str, updates["system_prompt"])
        if "skills" in updates:
            agent.skill_ids = cast(list[str], updates["skills"])
        if "skill_configs" in updates:
            agent.skill_configs = cast(dict[str, dict], updates["skill_configs"])
        if "built_in" in updates:
            built_in = cast(bool, updates["built_in"])
            agent.is_public = built_in
            agent.is_built_in = built_in
        if "max_iterations" in updates:
            agent.max_iterations = cast(int, updates["max_iterations"])
        if "tools_allowed" in updates:
            agent.enabled_builtin_tools = persist_enabled_builtin_tools(
                updates["tools_allowed"]
            )
        if "memory_policy" in updates:
            agent.memory_policy = memory_policy_to_dict(cast(AgentMemoryPolicy | None, updates["memory_policy"]))
        if "workspace_policy" in updates:
            agent.workspace_policy = cast(str, updates["workspace_policy"])
        if "cron_post_run_verify" in updates:
            agent.cron_post_run_verify = bool(updates["cron_post_run_verify"])
        if "command_bindings" in updates:
            raw_bindings = updates["command_bindings"]
            if raw_bindings is None:
                agent.command_bindings = None
            elif isinstance(raw_bindings, list):
                agent.command_bindings = [
                    {
                        "command_name": b.command_name,
                        "skill_ids": list(b.skill_ids),
                        "description": b.description,
                        "aliases": list(b.aliases),
                        "instruction": b.instruction,
                    }
                    if isinstance(b, CommandBinding)
                    else b
                    for b in raw_bindings
                ]

        if "metadata" in updates:
            metadata = cast(dict[str, object], updates["metadata"])
            if "mcp_ids" in metadata:
                agent.mcp_servers = cast(list[str], metadata["mcp_ids"])
            if "mcp_tool_selections" in metadata:
                raw_sel = metadata["mcp_tool_selections"]
                agent.mcp_tool_selections = cast(dict[str, list[str]], raw_sel) if isinstance(raw_sel, dict) else None
            if "enabled_builtin_tools" in metadata:
                agent.enabled_builtin_tools = persist_enabled_builtin_tools(
                    metadata["enabled_builtin_tools"]
                )
            if "home_directory" in metadata:
                agent.home_directory = cast(str | None, metadata["home_directory"])
            if "prompt_mode" in metadata:
                agent.prompt_mode = cast(str, metadata["prompt_mode"])
            if "personality_style" in metadata:
                agent.personality_style = cast(str, metadata["personality_style"])
            if "security_overrides" in metadata:
                agent.security_overrides = cast(dict[str, object] | None, metadata["security_overrides"])
            if "subagent_ids" in metadata:
                agent.subagent_ids = cast(list[str], metadata["subagent_ids"])
            if "workspace_policy" in metadata:
                agent.workspace_policy = cast(str, metadata["workspace_policy"])
            if "engine_params" in metadata:
                engine_params = metadata["engine_params"]
                if engine_params is None or isinstance(engine_params, dict):
                    agent.engine_params = engine_params
            if "auto_restore_domains" in metadata:
                raw_ar = metadata["auto_restore_domains"]
                if raw_ar is None:
                    agent.auto_restore_domains = None
                elif isinstance(raw_ar, list):
                    agent.auto_restore_domains = [str(x) for x in raw_ar]
            if "suggestion_prompts" in metadata:
                raw_sp = metadata["suggestion_prompts"]
                if raw_sp is None:
                    agent.suggestion_prompts = None
                elif isinstance(raw_sp, list):
                    agent.suggestion_prompts = [str(x) for x in raw_sp]
            if "openapi_services" in metadata:
                raw_os = metadata["openapi_services"]
                agent.openapi_services = raw_os if isinstance(raw_os, list) else None
            if "agent_type" in metadata:
                agent.agent_type = str(metadata["agent_type"])
            if "session_policy" in metadata:
                raw_sp = metadata["session_policy"]
                agent.session_policy = raw_sp if isinstance(raw_sp, dict) else None
            if "notify_targets" in metadata:
                raw_nt = metadata["notify_targets"]
                agent.notify_targets = raw_nt if isinstance(raw_nt, list) else None
            if "tool_gateway_config" in metadata:
                gateway_config = metadata["tool_gateway_config"]
                if gateway_config and isinstance(gateway_config, dict) and gateway_config.get("auth_token"):
                    # Only encrypt if it's not already encrypted (crude check: if it doesn't look like base64 AES-GCM)
                    # ConfigCrypto format is usually base64. Let's just encrypt it.
                    # Wait, if the user sends the SAME config back, it might be the placeholder or already encrypted.
                    # Usually frontend sends raw token or empty.
                    raw_token = gateway_config["auth_token"]
                    if not raw_token.startswith(
                        "ey"
                    ):  # Basic heuristic to avoid double encrypting if frontend sends back encrypted
                        try:
                            from myrm_agent_harness.utils.crypto.config_crypto import ConfigCrypto

                            from app.core.security.master_key import MasterKeyProvider

                            master_key = MasterKeyProvider.get_master_key()
                            derived_key = ConfigCrypto.derive_key(master_key)

                            encrypted_token = ConfigCrypto.encrypt_value({"value": raw_token}, derived_key)
                            gateway_config["auth_token"] = encrypted_token
                        except Exception as e:
                            import logging

                            logging.getLogger(__name__).error(f"Failed to encrypt gateway auth_token: {e}")
                            gateway_config.pop("auth_token", None)
                agent.tool_gateway_config = gateway_config
            if "mounted_skill_ids" in metadata:
                agent.mounted_skill_ids = cast(list[str], metadata["mounted_skill_ids"])
            if "browser_source" in metadata:
                agent.browser_source = cast(str | None, metadata["browser_source"])
            if "dialog_policy" in metadata:
                agent.dialog_policy = cast(str | None, metadata["dialog_policy"])
            if "session_recording" in metadata:
                agent.session_recording = cast(str | None, metadata["session_recording"])

        # Increment version and save history if core fields changed
        if any(k in updates for k in ["system_prompt", "display_name", "description"]) or (
            "metadata" in updates and "personality_style" in updates["metadata"]
        ):
            # Optimistic locking handles the version increment automatically
            # We just need to flush to get the new version number
            from fastapi import HTTPException
            from sqlalchemy.orm.exc import StaleDataError

            try:
                await db.flush()
            except StaleDataError as e:
                raise HTTPException(
                    status_code=409,
                    detail="Agent profile was modified by another request. Please refresh and try again.",
                ) from e

            from app.database.models.agent_history import AgentProfileHistory

            history_record = AgentProfileHistory(
                id=uuid.uuid4().hex,
                agent_id=agent.id,
                version=agent.version,
                name=agent.name,
                description=agent.description,
                system_prompt=agent.system_prompt,
                personality_style=agent.personality_style,
                snapshot_data={
                    "model_config": agent.model_config,
                    "model_selection": agent.model_selection,
                    "skill_ids": agent.skill_ids,
                    "mcp_servers": agent.mcp_servers,
                    "enabled_builtin_tools": agent.enabled_builtin_tools,
                    "auto_restore_domains": agent.auto_restore_domains or [],
                },
            )
            db.add(history_record)

        try:
            await db.flush()
        except StaleDataError as e:
            from fastapi import HTTPException

            raise HTTPException(
                status_code=409,
                detail="Agent profile was modified by another request. Please refresh and try again.",
            ) from e

        await db.refresh(agent)
        return AgentRepository._agent_to_profile(agent)

    @staticmethod
    async def delete_profile(db: AsyncSession, agent_id: str) -> bool:
        result = await db.execute(select(Agent).where(Agent.id == agent_id))
        agent = result.scalar_one_or_none()
        if agent:
            await db.delete(agent)
            return True
        return False
