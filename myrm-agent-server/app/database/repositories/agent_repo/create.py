"""[INPUT]
- app.database.models / harness profile types (POS: ORM + domain types)
- app.core.security.master_key::MasterKeyProvider (POS: 安全金库密钥派生模块)

[OUTPUT]
- CreateMixin

[POS]
AgentRepository mixin: profile creation and deletion; gateway auth tokens are encrypted only with an
available master key, and a locked vault drops the token instead of storing plaintext.
"""

from __future__ import annotations

import uuid

from myrm_agent_harness.backends.profiles.types import AgentProfile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_agents.personality_templates import DEFAULT_PERSONALITY_STYLE
from app.core.memory.adapters.policy import memory_policy_to_dict
from app.database.models import Agent
from app.services.agent.builtin_specs.builtin_tool_ids import persist_enabled_builtin_tools

from .mapping import MappingMixin


class CreateMixin:
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

                master_key = await MasterKeyProvider.ensure_master_key(grace_sec=0)
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

        full_model_selection = meta.pop("model_selection_full", None) or meta.pop("_model_selection_full", None)
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
            trusted_desktop_apps=list(meta.get("trusted_desktop_apps", []) or []),
            responsibility_scope=meta.get("responsibility_scope") if isinstance(meta.get("responsibility_scope"), str) else None,
            owner_label=meta.get("owner_label") if isinstance(meta.get("owner_label"), str) else None,
            acceptance_criteria=(
                [str(x) for x in meta["acceptance_criteria"]] if isinstance(meta.get("acceptance_criteria"), list) else None
            ),
            allow_discovery=(bool(meta["allow_discovery"]) if meta.get("allow_discovery") is not None else True),
            enabled_builtin_tools=persist_enabled_builtin_tools(meta.get("enabled_builtin_tools", profile.tools_allowed)),
            browser_source=meta.get("browser_source"),
            dialog_policy=meta.get("dialog_policy"),
            session_recording=meta.get("session_recording"),
            auto_restore_domains=auto_restore_val,
            security_overrides=meta.get("security_overrides"),
            default_security_preset=meta.get("default_security_preset"),
            engine_params=MappingMixin._prepare_engine_params(meta),
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
        return MappingMixin._agent_to_profile(agent)

    @staticmethod
    async def delete_profile(db: AsyncSession, agent_id: str) -> bool:
        result = await db.execute(select(Agent).where(Agent.id == agent_id))
        agent = result.scalar_one_or_none()
        if agent:
            await db.delete(agent)
            return True
        return False
