"""Database Subagent Catalog Implementation.

[INPUT]
- myrm_agent_harness.agent.security::CredentialTrack (POS: the credential pool a turn draws on)
- app.ai_agents.subagent_presets::load_subagent_presets (POS: the YAML subagent presets)
- app.ai_agents.custom_agent_factory::CustomAgentFactory (POS: builds the SkillAgent of a database custom agent)
- app.services.agent.agent_service::AgentService (POS: the stored custom agent profiles)

[OUTPUT]
- DatabaseSubagentCatalog: SubagentCatalog over YAML presets, in-memory JIT configs and database custom agents

[POS]
Resolves subagent configurations from YAML presets or database.
When loading custom agents from DB as subagents:
  - Injects CustomAgentFactory to build a full SkillAgent (with skills, memory, MCP)
  - Enforces LEAF control scope (no recursive delegation)
  - Enforces READ_ONLY_GLOBAL memory isolation (prevent concurrent state pollution),
    or EPHEMERAL_SESSION when the owning chat is incognito so no memory is read or written
  - Gates the agent's skills for the delegating turn's credential track

For a YAML preset or an in-memory (blueprint) config that names a model, injects a ModelResolver so config.model
resolves to an LLM instance of its own; a config that names no model runs on the delegating agent's LLM.
"""

import logging
from dataclasses import replace

from myrm_agent_harness.agent.security import CredentialTrack
from myrm_agent_harness.agent.sub_agents.types import (
    ControlScope,
    MemoryIsolationPolicy,
    SubagentConfig,
    WorkspacePolicy,
)

from app.ai_agents.subagent_presets import load_subagent_presets
from app.platform_utils import get_session_factory
from app.services.agent.agent_service import AgentService

logger = logging.getLogger(__name__)


class _LLMModelResolver:
    """ModelResolver implementation using the business layer's model resolver.

    Resolves model_name (routed ``provider/model`` form like "openai/gpt-4o-mini") to a
    BaseChatModel by looking up the user's provider config for API keys.

    The harness always passes its routing hints; they are accepted and ignored because this resolver is only
    injected for a preset that names its model, and a named model is resolved by name.
    """

    def __init__(self) -> None:
        pass

    async def resolve(
        self,
        model_name: str,
        complexity_tier: str | None = None,
        task_description: str | None = None,
    ) -> object:
        from myrm_agent_harness.toolkits.llms import llm_manager

        from app.core.channel_bridge.config_loader import load_user_configs
        from app.core.channel_bridge.model_resolver import resolve_model_config

        configs = await load_user_configs()
        providers_dict = configs.providers_dict if configs else None
        model_cfg = resolve_model_config(providers_dict, model_override=model_name)
        return await llm_manager.get_llm_from_config(model_cfg, api_keys=getattr(model_cfg, "api_keys", None))


class DatabaseSubagentCatalog:
    """Subagent catalog: YAML presets + database custom agents.

    For YAML presets and in-memory configs that name a model, injects model_resolver so config.model is resolved.
    For DB custom agents, injects CustomAgentFactory so that build_child_agent()
    creates a SkillAgent with full capabilities instead of a bare BaseAgent.

    Scope restriction: ``bound_agent_ids`` is the complete delegation grant. When it is a list,
    only those IDs (plus JIT workers) are available; an empty list grants nothing. ``None`` is
    reserved for controlled internal callers that resolve a specific YAML preset without a chat
    grant (for example the cron post-run verifier); it is not a user-facing "all presets" mode.

    Incognito: a delegated sub-agent cannot see the chat's incognito flag (its parent is the runtime
    SkillAgent), so the owner of the chat tells the catalog and DB agents are configured without memory.

    Credential track: a delegated sub-agent runs inside the delegating turn and is handed that turn's
    credentials, so the owner of the turn tells the catalog which track it is on and DB agents gate their
    skills for it. Only a channel turn in a team-shared topic is on another track than the owner's own; the
    callers outside a channel turn (cron verifier, web stream lane) keep the default.
    """

    def __init__(
        self,
        bound_agent_ids: list[str] | None = None,
        jit_configs: dict[str, SubagentConfig] | None = None,
        *,
        incognito_mode: bool = False,
        credential_track: CredentialTrack = CredentialTrack.PERSONAL,
    ):
        self._bound_agent_ids = set(bound_agent_ids) if bound_agent_ids is not None else None
        self._jit_configs = jit_configs or {}
        self._credential_track = credential_track
        self._db_agent_memory_isolation = (
            MemoryIsolationPolicy.EPHEMERAL_SESSION if incognito_mode else MemoryIsolationPolicy.READ_ONLY_GLOBAL
        )
        self._model_resolver = _LLMModelResolver()

        try:
            self._yaml_configs = load_subagent_presets()
        except Exception as e:
            logger.warning("Failed to load YAML subagent configs: %s", e)
            self._yaml_configs = {}

    async def resolve(self, type_id: str) -> SubagentConfig | None:
        """Resolve a subagent configuration by type_id or agent_id."""
        if type_id in self._jit_configs:
            cfg = self._jit_configs[type_id]
            if cfg.model and cfg.model_resolver is None:
                return replace(cfg, model_resolver=self._model_resolver)
            return cfg

        if type_id in self._yaml_configs:
            if self._bound_agent_ids is not None and type_id not in self._bound_agent_ids:
                logger.warning("YAML subagent '%s' is not in bound_agent_ids, rejecting", type_id)
                return None
            cfg = self._yaml_configs[type_id]
            if cfg.model and cfg.model_resolver is None:
                return replace(cfg, model_resolver=self._model_resolver)
            return cfg

        if self._bound_agent_ids is not None and type_id not in self._bound_agent_ids:
            logger.warning("Agent '%s' not in bound_agent_ids, rejecting", type_id)
            return None

        try:
            session_factory = get_session_factory()
            async with session_factory() as _db:
                agent_profile = await AgentService.get_agent_by_id(type_id)
                if not agent_profile:
                    return None

                from app.ai_agents.custom_agent_factory import CustomAgentFactory

                factory = CustomAgentFactory(
                    agent_id=type_id,
                    agent_profile=agent_profile,
                    credential_track=self._credential_track,
                )

                max_turns = agent_profile.max_iterations or 25
                workspace_policy = (
                    WorkspacePolicy.READ_ONLY_SANDBOX
                    if (agent_profile.metadata or {}).get("workspace_policy") == "READ_ONLY_SANDBOX"
                    else WorkspacePolicy.INHERIT
                )

                return SubagentConfig(
                    system_prompt=agent_profile.system_prompt or "",
                    description=agent_profile.description or "",
                    display_name=agent_profile.display_name or "",
                    model=agent_profile.model,
                    max_turns=max_turns,
                    control_scope=ControlScope.LEAF,
                    memory_isolation=self._db_agent_memory_isolation,
                    max_spawn_depth=0,
                    workspace_policy=workspace_policy,
                    agent_factory=factory,
                )
        except Exception as e:
            logger.error("Failed to resolve subagent from database for type_id=%s: %s", type_id, e)
            return None

    async def list_available(self) -> list[str]:
        """List the delegation grant, in stable order and without duplicates.

        ``bound_agent_ids`` is authoritative: when it is a list, YAML presets are listed only
        because they are in that list. ``None`` is the unscoped cron verifier path, which may
        resolve a YAML preset and list the database catalog.
        """
        ordered: dict[str, None] = dict.fromkeys(self._jit_configs)

        if self._bound_agent_ids is not None:
            for type_id in sorted(self._bound_agent_ids):
                if type_id in self._jit_configs or type_id in self._yaml_configs:
                    ordered.setdefault(type_id, None)
                    continue
                try:
                    profile = await AgentService.get_agent_by_id(type_id)
                except Exception as e:
                    logger.error("Failed to validate bound subagent '%s': %s", type_id, e)
                    continue
                if profile is not None:
                    ordered.setdefault(type_id, None)
            return list(ordered)

        for type_id in self._yaml_configs:
            ordered.setdefault(type_id, None)
        try:
            session_factory = get_session_factory()
            async with session_factory() as _db:
                profiles, _ = await AgentService.get_agent_list(page=1, page_size=1000)
                for profile in profiles:
                    ordered.setdefault(profile.id, None)
        except Exception as e:
            logger.error("Failed to list available subagents from database: %s", e)

        return list(ordered)
