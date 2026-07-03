"""Local Eval Executor for the Server Layer.

[INPUT]
- myrm_agent_harness.eval.protocol::AgentExecutor, AgentResponse
- app.ai_agents.agents::AgentFactory, GeneralAgentParams
- app.core.channel_bridge.config_loader::load_user_configs
- app.core.channel_bridge.config_parsers::extract_*

[OUTPUT]
- LocalEvalExecutor: implements AgentExecutor for local evaluation.

[POS]
Adapts the Server's AgentFactory to the Harness's Eval framework.
Provides a clean, isolated execution environment for each eval case.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import TYPE_CHECKING

from myrm_agent_harness.eval.protocols import AgentResponse
from myrm_agent_harness.toolkits.code_execution.config import ExecutionConfig
from myrm_agent_harness.toolkits.code_execution.executors.base import CodeExecutor
from myrm_agent_harness.toolkits.code_execution.executors.local import LocalExecutor

from app.ai_agents.agents import AgentFactory, GeneralAgentParams
from app.core.channel_bridge.config_loader import load_user_configs
from app.core.channel_bridge.config_parsers import (
    extract_fallback_model_configs,
    extract_lite_model_config,
    extract_mcp_configs,
    extract_retrieval_models,
    extract_user_instructions,
    verify_search_service_available,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    pass


class LocalEvalExecutor:
    """Executes Agent eval cases using the Server's Agent configuration."""

    def __init__(self, profile_id: str | None = None) -> None:
        self.profile_id = profile_id
        self._sandbox_executors: dict[str, CodeExecutor] = {}
        self._session_id: str | None = None

    async def create_session(self) -> str:
        """Create a new session ID.

        In a real sandbox environment, this might trigger a snapshot or container spin-up.
        For eval, we generate a unique chat ID and create a dedicated physical
        workspace directory to ensure true concurrency isolation per case.
        """
        from pathlib import Path

        self._session_id = f"eval_{uuid.uuid4().hex[:8]}"

        # Create an isolated workspace directory for this evaluation session
        workspace_dir = (Path(".myrm/eval_workspaces") / self._session_id).resolve()
        workspace_dir.mkdir(parents=True, exist_ok=True)

        # Initialize a sandbox executor for this session if needed by assertions
        # We use the local executor for testing purposes and bind it to the isolated workspace
        self._sandbox_executors[self._session_id] = LocalExecutor(ExecutionConfig(), workspace_path=str(workspace_dir))

        return self._session_id

    def get_sandbox_executor(self, session_id: str | None = None) -> CodeExecutor | None:
        """Return the SandboxExecutor for evaluating state assertions."""
        if session_id and session_id in self._sandbox_executors:
            return self._sandbox_executors[session_id]
        if self._session_id and self._session_id in self._sandbox_executors:
            return self._sandbox_executors[self._session_id]
        return None

    async def execute(self, message: str, *, session_id: str | None = None) -> AgentResponse:
        """Execute a single eval case."""
        from pathlib import Path

        chat_id = session_id or self._session_id or f"eval_{uuid.uuid4().hex[:8]}"

        # Resolve the isolated physical workspace directory for this execution
        workspace_dir = (Path(".myrm/eval_workspaces") / chat_id).resolve()
        workspace_dir.mkdir(parents=True, exist_ok=True)

        # Load user configs to test their specific agent setup
        configs = await load_user_configs()

        embedding_cfg, reranker_cfg = extract_retrieval_models(configs.retrieval_dict)
        mcp_configs = extract_mcp_configs(configs.mcp_dict)
        lite_model_cfg = extract_lite_model_config(configs.providers_dict)
        fallback_model_cfg, fallback_lite_model_cfg = extract_fallback_model_configs(configs.providers_dict)
        user_instructions = extract_user_instructions(configs.personal_settings_dict)

        agent_skill_ids = []
        agent_subagent_ids = None
        agent_security_raw: dict[str, object] = {"yolo_mode_enabled": True}
        agent_max_iterations = None
        agent_memory_policy = None
        agent_engine_params = None

        agent_model_override: str | None = None
        from app.services.agent.profile_resolver import (
            DEFAULT_ENABLED_BUILTIN_TOOLS,
            apply_agent_baseline_tool_flags,
            resolve_builtin_tool_flags,
        )

        enabled_builtin_tools: list[str] = list(DEFAULT_ENABLED_BUILTIN_TOOLS)
        auto_restore_domains: list[str] = []
        memory_decay_profile: str | None = None

        if self.profile_id:
            from app.services.agent.profile_resolver import get_agent_profile_resolver

            resolved = await get_agent_profile_resolver().resolve(self.profile_id)
            if resolved:
                if resolved.system_prompt:
                    user_instructions = (
                        f"{user_instructions}\n\n{resolved.system_prompt}" if user_instructions else resolved.system_prompt
                    )
                agent_skill_ids = list(resolved.skill_ids)
                agent_subagent_ids = list(resolved.subagent_ids) if resolved.subagent_ids else None
                if resolved.security_overrides:
                    for _k, _v in resolved.security_overrides.items():
                        agent_security_raw[str(_k)] = _v
                agent_max_iterations = resolved.max_iterations
                agent_memory_policy = resolved.memory_policy
                agent_engine_params = resolved.engine_params
                agent_model_override = resolved.model
                enabled_builtin_tools = list(resolved.enabled_builtin_tools)
                auto_restore_domains = list(resolved.auto_restore_domains)
                raw_decay = resolved.memory_decay_profile
                memory_decay_profile = raw_decay if isinstance(raw_decay, str) else None

                if mcp_configs:
                    from app.services.agent.params.mcp_selection import apply_agent_mcp_selection

                    mcp_configs = apply_agent_mcp_selection(
                        mcp_configs,
                        mcp_ids=resolved.mcp_ids or None,
                        mcp_tool_selections=resolved.mcp_tool_selections or None,
                    )

        memory_shared_context_ids: list[str] = []
        try:
            from app.services.memory.shared_context import resolve_shared_context_ids

            memory_shared_context_ids = await resolve_shared_context_ids(
                agent_id=self.profile_id,
                channel_id="eval",
                conversation_id=chat_id,
            )
        except Exception as e:
            logger.warning("Failed to resolve shared memory contexts for eval run: %s", e)

        from myrm_agent_harness.toolkits.retriever.embedding.factory import EmbeddingConfig
        from myrm_agent_harness.toolkits.retriever.reranker.factory import RerankerConfig

        GeneralAgentParams.model_rebuild(
            _types_namespace={
                "EmbeddingConfig": EmbeddingConfig,
                "RerankerConfig": RerankerConfig,
            }
        )

        # Resolve model: agent-specific model > global default
        if agent_model_override:
            from app.core.channel_bridge.model_resolver import enrich_model_context_window, resolve_model_config

            eval_model_cfg = resolve_model_config(
                configs.providers_dict,
                model_override=agent_model_override,
            )
            eval_model_cfg = enrich_model_context_window(eval_model_cfg, configs.providers_dict)
        else:
            eval_model_cfg = configs.model_cfg

        params = GeneralAgentParams(
            query=message,
            model_cfg=eval_model_cfg,
            fallback_model_cfg=fallback_model_cfg,
            lite_model_cfg=lite_model_cfg,
            fallback_lite_model_cfg=fallback_lite_model_cfg,
            search_service_cfg=configs.search_cfg,
            mcp_cfg=mcp_configs or None,
            user_instructions=user_instructions,
            agent_id=self.profile_id,
            chat_id=chat_id,
            embedding_config=embedding_cfg,
            reranker_config=reranker_cfg,
            channel_name="eval",
            enable_web_search=configs.search_is_user_configured and await verify_search_service_available(configs.search_cfg),
            **apply_agent_baseline_tool_flags(resolve_builtin_tool_flags(enabled_builtin_tools)),
            auto_restore_domains=auto_restore_domains,
            unattended_mode=True,
            agent_skill_ids=agent_skill_ids,
            subagent_ids=agent_subagent_ids,
            agent_security_raw=agent_security_raw,
            max_iterations=agent_max_iterations,
            memory_policy=agent_memory_policy,
            memory_decay_profile=memory_decay_profile,
            engine_params=agent_engine_params,
            memory_shared_context_ids=memory_shared_context_ids,
            declared_allowed_roots=(str(workspace_dir),),
        )

        agent = AgentFactory.create_general_agent(params)

        start_time = time.perf_counter()
        chunks: list[str] = []
        tools_called: list[str] = []
        total_input_tokens = 0
        total_output_tokens = 0

        try:
            async for event in agent.process_stream(query=message, chat_id=chat_id):
                event_type = event.get("type", "")

                if event_type == "message" and isinstance(event.get("data"), str):
                    chunks.append(str(event["data"]))
                elif event_type == "tasks_steps":
                    tool_name = str(event.get("tool_name", "")) or str(event.get("step_key", ""))
                    if tool_name:
                        tools_called.append(tool_name)
                elif event_type == "token_usage":
                    data = event.get("data")
                    if isinstance(data, dict):
                        total_input_tokens += int(data.get("input_tokens") or 0)
                        total_output_tokens += int(data.get("output_tokens") or 0)
        finally:
            await agent.close()

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        total_tokens = total_input_tokens + total_output_tokens

        return AgentResponse(
            answer="".join(chunks),
            tools_called=tools_called,
            extra_timings={"execution_ms": elapsed_ms},
            token_usage={
                "input_tokens": total_input_tokens,
                "output_tokens": total_output_tokens,
                "total_tokens": total_tokens,
            },
        )
