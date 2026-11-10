"""[INPUT]
- app.database.models / harness profile types (POS: ORM + domain types)

[OUTPUT]
- MappingMixin

[POS]
AgentRepository mixin: ORM agent -> AgentProfile conversion and engine-params projection.
"""

from __future__ import annotations

from myrm_agent_harness.backends.profiles.types import AgentProfile, CommandBinding

from app.core.memory.adapters.policy import memory_policy_from_dict
from app.database.dto import normalize_workspace_policy
from app.database.models import Agent


class MappingMixin:
    @staticmethod
    def _agent_to_profile(agent: Agent) -> AgentProfile:
        """Convert Agent DB model to AgentProfile dataclass."""
        bindings: list[CommandBinding] | None = None
        if agent.command_bindings:
            bindings = [
                CommandBinding(
                    command_name=b["command_name"],
                    skill_ids=(tuple(b["skill_ids"]) if "skill_ids" in b else (b["skill_id"],) if "skill_id" in b else ()),
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
                "security_overrides": agent.security_overrides,
                "default_security_preset": agent.default_security_preset,
                "subagent_ids": agent.subagent_ids,
                "trusted_desktop_apps": list(getattr(agent, "trusted_desktop_apps", []) or []),
                "responsibility_scope": getattr(agent, "responsibility_scope", None),
                "owner_label": getattr(agent, "owner_label", None),
                "acceptance_criteria": list(getattr(agent, "acceptance_criteria", None) or []),
                "workspace_policy": normalize_workspace_policy(agent.workspace_policy),
                "allow_discovery": (bool(agent.allow_discovery) if agent.allow_discovery is not None else True),
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
                "is_pareto_preset": bool((agent.engine_params or {}).get("is_pareto_preset", False))
                if isinstance(agent.engine_params, dict)
                else False,
                "cost_reduction_ratio": (agent.engine_params or {}).get("cost_reduction_ratio")
                if isinstance(agent.engine_params, dict)
                else None,
            },
            built_in=agent.is_built_in or agent.is_public,
            created_at=agent.created_at,
            updated_at=agent.updated_at,
        )

    @staticmethod
    def _prepare_engine_params(meta: dict[str, object]) -> dict[str, object] | None:
        """Combine engine_params with top-level is_pareto_preset / cost_reduction_ratio metadata."""
        ep = meta.get("engine_params")
        engine_params = dict(ep) if isinstance(ep, dict) else {}

        if meta.get("is_pareto_preset") is not None:
            engine_params["is_pareto_preset"] = bool(meta["is_pareto_preset"])
        if meta.get("cost_reduction_ratio") is not None:
            engine_params["cost_reduction_ratio"] = float(meta["cost_reduction_ratio"])  # type: ignore[arg-type]

        return engine_params or None
