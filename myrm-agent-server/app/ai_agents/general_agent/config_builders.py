"""Config builders for General Agent

Contains builder functions for execution, privacy, and other configurations.
"""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langchain_core.language_models.chat_models import BaseChatModel
    from myrm_agent_harness.agent.security.types import PrivacyRoutingConfig
    from myrm_agent_harness.backends.skills.protocols import SkillBackend as SkillBackendProtocol
    from myrm_agent_harness.toolkits.code_execution.config import ExecutionConfig
    from myrm_agent_harness.toolkits.llms.routing import PrivacyRoutingModel

logger = logging.getLogger(__name__)


def build_privacy_routing_config(privacy_routing_raw: dict[str, object] | None) -> "PrivacyRoutingConfig | None":
    """Build PrivacyRoutingConfig from raw frontend config, or None if not configured."""
    raw = privacy_routing_raw
    if not raw or not raw.get("localModel"):
        return None

    from myrm_agent_harness.agent.security.types import PrivacyRoutingConfig

    return PrivacyRoutingConfig(
        local_model=str(raw["localModel"]),
        local_base_url=str(raw["localBaseUrl"]) if raw.get("localBaseUrl") else None,
        local_api_key=str(raw["localApiKey"]) if raw.get("localApiKey") else None,
        s2_strategy=str(raw.get("s2Strategy", "cloud_after_redact")),

        s3_strategy=str(raw.get("s3Strategy", "local")),

        local_fallback=str(raw.get("localFallback", "block")),

    )


def wrap_with_privacy_routing(
    cloud_llm: "BaseChatModel",
    routing_config: "PrivacyRoutingConfig",
) -> "PrivacyRoutingModel":
    """Wrap a cloud LLM with PrivacyRoutingModel using the given config."""
    from myrm_agent_harness.toolkits.llms import create_litellm_model
    from myrm_agent_harness.toolkits.llms.routing import PrivacyRoutingModel

    local_llm = create_litellm_model(
        model=routing_config.local_model,
        base_url=routing_config.local_base_url,
        api_key=routing_config.local_api_key or "",
        temperature=0.2,
        streaming=True,
    )
    return PrivacyRoutingModel(
        cloud_llm=cloud_llm,
        local_llm=local_llm,
        routing_config=routing_config,
    )


def build_execution_config(code_execution_allow_network: bool | None) -> "ExecutionConfig":
    """Build per-session ExecutionConfig, applying user's network preference."""
    from myrm_agent_harness.toolkits.code_execution.config import (
        ExecutionConfig,
        NetworkConfig,
        get_execution_config,
    )

    base = get_execution_config()
    if code_execution_allow_network is None:
        return base

    return ExecutionConfig(
        mode=base.mode,
        local=base.local,
        mcp_proxy=base.mcp_proxy,
        network=NetworkConfig(
            allow_network=code_execution_allow_network,
            allowed_hosts=base.network.allowed_hosts,
        ),
    )


async def resolve_skill_env_map(
    skill_backend: "SkillBackendProtocol | None",
    skill_env_vars: dict[str, dict[str, str]],
) -> dict[str, dict[str, str]]:
    """Verify stored skill_env_vars against current installed skills.

    Removes environments for uninstalled skills and updates names if changed.
    This acts as a self-healing mechanism for user skill configs.
    """
    if not skill_backend or not skill_env_vars:
        return skill_env_vars

    try:
        all_skills = await skill_backend.list_skills()
        valid_map: dict[str, dict[str, str]] = {}
        for skill in all_skills:
            if skill.skill_id in skill_env_vars:
                valid_map[skill.name] = skill_env_vars[skill.skill_id]
        return valid_map
    except Exception as e:
        logger.warning(f"Failed to validate skill env map: {e}")
        return skill_env_vars
