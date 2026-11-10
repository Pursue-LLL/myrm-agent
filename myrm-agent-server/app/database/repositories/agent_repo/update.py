"""[INPUT]
- app.database.models / harness profile types (POS: ORM + domain types)

[OUTPUT]
- UpdateMixin

[POS]
AgentRepository mixin: profile update with optimistic-concurrency handling.
"""

from __future__ import annotations

import uuid
from typing import cast

from myrm_agent_harness.backends.profiles.types import AgentProfile, CommandBinding
from myrm_agent_harness.toolkits.memory.config import AgentMemoryPolicy
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.exc import StaleDataError

from app.core.memory.adapters.policy import memory_policy_to_dict
from app.database.models import Agent
from app.services.agent.builtin_specs.builtin_tool_ids import persist_enabled_builtin_tools

from .mapping import MappingMixin


class UpdateMixin:
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
            agent.enabled_builtin_tools = persist_enabled_builtin_tools(updates["tools_allowed"])
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

        if "metadata" in updates:
            metadata = cast(dict[str, object], updates["metadata"])
            if "mcp_ids" in metadata:
                agent.mcp_servers = cast(list[str], metadata["mcp_ids"])
            if "mcp_tool_selections" in metadata:
                raw_sel = metadata["mcp_tool_selections"]
                agent.mcp_tool_selections = cast(dict[str, list[str]], raw_sel) if isinstance(raw_sel, dict) else None
            if "enabled_builtin_tools" in metadata:
                agent.enabled_builtin_tools = persist_enabled_builtin_tools(metadata["enabled_builtin_tools"])
            if "home_directory" in metadata:
                agent.home_directory = cast(str | None, metadata["home_directory"])
            if "security_overrides" in metadata:
                agent.security_overrides = cast(dict[str, object] | None, metadata["security_overrides"])
            if "default_security_preset" in metadata:
                agent.default_security_preset = cast(str | None, metadata["default_security_preset"])
            if "subagent_ids" in metadata:
                agent.subagent_ids = cast(list[str], metadata["subagent_ids"])
            if "trusted_desktop_apps" in metadata and metadata["trusted_desktop_apps"] is not None:
                agent.trusted_desktop_apps = list(metadata["trusted_desktop_apps"])
            if "responsibility_scope" in metadata:
                raw_rs = metadata["responsibility_scope"]
                agent.responsibility_scope = raw_rs if isinstance(raw_rs, str) else None
            if "owner_label" in metadata:
                raw_ol = metadata["owner_label"]
                agent.owner_label = raw_ol if isinstance(raw_ol, str) else None
            if "acceptance_criteria" in metadata:
                raw_ac = metadata["acceptance_criteria"]
                agent.acceptance_criteria = [str(x) for x in raw_ac] if isinstance(raw_ac, list) else None
            if "allow_discovery" in metadata and metadata["allow_discovery"] is not None:
                agent.allow_discovery = bool(metadata["allow_discovery"])
            if "workspace_policy" in metadata:
                agent.workspace_policy = cast(str, metadata["workspace_policy"])
            if "engine_params" in metadata or "is_pareto_preset" in metadata or "cost_reduction_ratio" in metadata:
                agent.engine_params = MappingMixin._prepare_engine_params(metadata)
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
                            from myrm_agent_harness.utils.crypto.config_crypto import (
                                ConfigCrypto,
                            )

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
        if any(k in updates for k in ["system_prompt", "display_name", "description"]):
            # Optimistic locking handles the version increment automatically
            # We just need to flush to get the new version number
            from fastapi import HTTPException

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

        # Async session: refresh ORM row after flush so timestamp columns load in-context.
        await db.refresh(agent)
        return MappingMixin._agent_to_profile(agent)
