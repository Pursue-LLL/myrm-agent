"""Kanban TaskRunner — bridges KanbanTask to the Agent execution pipeline.

Implements the ``TaskRunner`` protocol from the harness layer, wiring each
task through ``AgentProfileResolver`` → ``AgentFactory`` → ``GeneralAgent``
so that WorkBoard tasks execute with the full agent profile (model, skills,
tools, memory, security).

[INPUT]
- myrm_agent_harness.toolkits.kanban.protocols::TaskRunner (POS: Harness protocol.)
- myrm_agent_harness.toolkits.kanban.context_builder::build_task_context (POS: Worker context.)
- myrm_agent_harness.toolkits.kanban.types::KanbanTask, TaskTimeoutError (POS: Kanban domain types.)
- task_runner_stream::build_multimodal_query (POS: Multimodal query assembly.)
- task_runner_worktree::resolve_workspace, cleanup_worktree (POS: Git worktree isolation.)
- task_runner_profile::resolve_agent_profile (POS: Agent profile resolution.)

[OUTPUT]
- KanbanTaskRunner: Concrete TaskRunner implementation.

[POS]
Server-layer TaskRunner that executes kanban tasks through the agent pipeline.
"""

from __future__ import annotations

import asyncio
import logging
import time

from myrm_agent_harness.toolkits.kanban.context_builder import build_task_context
from myrm_agent_harness.toolkits.kanban.protocols import KanbanStore
from myrm_agent_harness.toolkits.kanban.types import KanbanTask, TaskTimeoutError

from app.services.agent.profile_resolver import (
    DEFAULT_ENABLED_BUILTIN_TOOLS,
    resolve_builtin_tool_flags,
)
from app.services.kanban.task_runner_profile import (
    _ResolvedProfile,
    resolve_agent_profile,
)
from app.services.kanban.task_runner_stream import (
    _classify_content_type,
    _StreamAccumulator,
    build_multimodal_query,
)
from app.services.kanban.task_runner_worktree import cleanup_worktree, resolve_workspace

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_SECONDS = 600
_BACKGROUND_TASK_TIMEOUT_SECONDS = 3600
_CHANNEL_NAME = "kanban"

__all__ = ["KanbanTaskRunner", "_ResolvedProfile", "_classify_content_type"]


class KanbanTaskRunner:
    """Concrete TaskRunner that executes tasks through the Agent pipeline."""

    def __init__(
        self,
        store: KanbanStore,
        *,
        timeout_seconds: int = _DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._store = store
        self._timeout_seconds = timeout_seconds

    async def run(self, task: KanbanTask) -> tuple[bool, str]:
        context = await build_task_context(self._store, task.task_id)
        profile = await resolve_agent_profile(task.agent_id)
        query_input = await build_multimodal_query(task, context)
        workspace_root = await resolve_workspace(self._store, task)

        is_background_task = (task.metadata or {}).get("background_source") == "btw"
        default_timeout = _BACKGROUND_TASK_TIMEOUT_SECONDS if is_background_task else self._timeout_seconds
        effective_timeout = task.max_runtime_seconds or default_timeout

        self._register_background_tokens(task)
        t0 = time.monotonic()
        try:
            return await asyncio.wait_for(
                self._execute_agent(task, query_input, profile, workspace_root),
                timeout=effective_timeout,
            )
        except asyncio.TimeoutError:
            elapsed = time.monotonic() - t0
            logger.warning(
                "Kanban task %s timed out after %.0fs (limit %ds)",
                task.task_id[:8],
                elapsed,
                effective_timeout,
            )
            raise TaskTimeoutError(
                task_id=task.task_id,
                elapsed_seconds=elapsed,
                limit_seconds=effective_timeout,
            ) from None
        except Exception as exc:
            logger.warning("Kanban task %s failed: %s", task.task_id[:8], exc)
            return False, str(exc)
        finally:
            self._unregister_background_tokens(task)

    def _register_background_tokens(self, task: KanbanTask) -> None:
        if (task.metadata or {}).get("background_source") != "btw":
            return
        try:
            from myrm_agent_harness.utils.runtime.cancellation import CancellationToken
            from myrm_agent_harness.utils.runtime.steering import SteeringToken

            from app.core.channel_bridge.setup import get_background_task_handler

            handler = get_background_task_handler()
            if handler:
                handler.register_runtime_tokens(
                    task.task_id,
                    CancellationToken(),
                    SteeringToken(),
                )
        except Exception:
            logger.debug("Could not register background tokens for %s", task.task_id[:8])

    def _unregister_background_tokens(self, task: KanbanTask) -> None:
        if (task.metadata or {}).get("background_source") != "btw":
            return
        try:
            from app.core.channel_bridge.setup import get_background_task_handler

            handler = get_background_task_handler()
            if handler:
                handler.unregister_runtime_tokens(task.task_id)
        except Exception:
            logger.debug("Could not unregister background tokens for %s", task.task_id[:8])

    async def cleanup_worktree(self, task: KanbanTask) -> None:
        await cleanup_worktree(self._store, task)

    async def _load_attachment_ids(self, task_id: str) -> list[str]:
        from app.services.kanban.task_runner_stream import _load_attachment_ids as load_ids

        return await load_ids(task_id)

    async def _extract_pdf_text(self, file_id: str) -> str:
        from app.services.kanban.task_runner_stream import _extract_pdf_text as extract_pdf

        return await extract_pdf(file_id)

    async def _extract_document_text(self, file_id: str) -> str:
        from app.services.kanban.task_runner_stream import _extract_document_text as extract_doc

        return await extract_doc(file_id)

    async def _build_multimodal_query(
        self,
        task: KanbanTask,
        text_context: str,
    ) -> str | list[dict[str, object]]:
        return await build_multimodal_query(
            task,
            text_context,
            load_attachment_ids=self._load_attachment_ids,
            extract_pdf=self._extract_pdf_text,
            extract_document=self._extract_document_text,
        )

    async def _resolve_profile(self, agent_id: str | None) -> _ResolvedProfile | None:
        return await resolve_agent_profile(agent_id)

    async def _execute_agent(
        self,
        task: KanbanTask,
        context: str | list[dict[str, object]],
        profile: _ResolvedProfile | None,
        workspace_root: str | None = None,
    ) -> tuple[bool, str]:
        from app.ai_agents.agents import AgentFactory, GeneralAgentParams
        from app.core.channel_bridge.config_loader import load_user_configs
        from app.core.channel_bridge.config_parsers import (
            extract_fallback_model_configs,
            extract_retrieval_models,
            verify_search_service_available,
        )
        from app.core.channel_bridge.model_resolver import (
            enrich_model_context_window,
            resolve_model_config,
        )

        user_cfgs = await load_user_configs()

        board = await self._store.get_board(task.board_id) if task.board_id else None
        zombie_timeout = board.settings.zombie_timeout_seconds if board and board.settings else 120

        embedding_cfg, reranker_cfg = extract_retrieval_models(user_cfgs.retrieval_dict)
        fallback_model_cfg, fallback_lite_model_cfg = extract_fallback_model_configs(
            user_cfgs.providers_dict,
        )

        from myrm_agent_harness.toolkits.retriever.embedding.factory import EmbeddingConfig
        from myrm_agent_harness.toolkits.retriever.reranker.factory import RerankerConfig

        GeneralAgentParams.model_rebuild(
            _types_namespace={
                "EmbeddingConfig": EmbeddingConfig,
                "RerankerConfig": RerankerConfig,
            },
        )

        security_config_raw = dict(user_cfgs.security_config_dict or {})
        if not security_config_raw.get("yolo_mode_enabled", False):
            security_config_raw["yolo_mode_enabled"] = True
            security_config_raw["yolo_mode_enabled_at"] = time.time()
            security_config_raw["yolo_mode_timeout"] = None

        model_override = profile.model if profile else None
        model_cfg = resolve_model_config(
            user_cfgs.providers_dict,
            model_override=model_override,
        )
        model_cfg = enrich_model_context_window(model_cfg, user_cfgs.providers_dict)

        memory_shared_context_ids: list[str] = []
        try:
            from app.services.memory.shared_context import resolve_shared_context_ids

            memory_shared_context_ids = await resolve_shared_context_ids(
                agent_id=task.agent_id,
                channel_id=_CHANNEL_NAME,
                conversation_id=task.task_id,
                task_id=task.task_id,
            )
        except Exception as exc:
            logger.warning(
                "Task %s: failed to resolve shared memory contexts: %s",
                task.task_id[:8],
                exc,
            )

        enabled_builtin_tools: list[str] = list(DEFAULT_ENABLED_BUILTIN_TOOLS)
        if profile is not None:
            enabled_builtin_tools = list(profile.enabled_builtin_tools)

        if "kanban" not in enabled_builtin_tools:
            enabled_builtin_tools.append("kanban")

        task_user_instructions: str | None = profile.system_prompt if profile else None
        agent_subagent_ids = list(profile.subagent_ids) if profile and profile.subagent_ids else None
        if profile and profile.agent_type == "team":
            from app.ai_agents.team_protocol import build_leader_protocol_prompt

            leader_protocol = await build_leader_protocol_prompt(
                agent_subagent_ids or [],
                leader_id=task.agent_id,
                dynamic_discovery=True,
            )
            task_user_instructions = (
                f"{task_user_instructions}\n\n{leader_protocol}" if task_user_instructions else leader_protocol
            )

        declared_roots: tuple[str, ...] = ()
        if workspace_root:
            declared_roots = (workspace_root,)

        params = GeneralAgentParams(
            query=context,
            model_cfg=model_cfg,
            fallback_model_cfg=fallback_model_cfg,
            fallback_lite_model_cfg=fallback_lite_model_cfg,
            search_service_cfg=user_cfgs.search_cfg,
            chat_id=task.task_id,
            agent_id=task.agent_id,
            embedding_config=embedding_cfg,
            reranker_config=reranker_cfg,
            security_config_raw=security_config_raw,
            agent_security_raw=profile.security_overrides if profile else None,
            channel_name=_CHANNEL_NAME,
            declared_allowed_roots=declared_roots,
            enable_web_search=(
                user_cfgs.search_is_user_configured and await verify_search_service_available(user_cfgs.search_cfg)
            ),
            kanban_tool_mode="worker",
            kanban_current_task_id=task.task_id,
            kanban_max_runtime_seconds=task.max_runtime_seconds,
            kanban_zombie_timeout_seconds=zombie_timeout,
            **resolve_builtin_tool_flags(enabled_builtin_tools),
            auto_restore_domains=list(profile.auto_restore_domains) if profile else [],
            unattended_mode=True,
            user_instructions=task_user_instructions,
            agent_skill_ids=list(dict.fromkeys((*(profile.skill_ids if profile else []), *task.extra_skill_ids))),
            subagent_ids=(list(profile.subagent_ids) if profile and profile.subagent_ids else None),
            max_iterations=profile.max_iterations if profile else None,
            memory_policy=profile.memory_policy if profile else None,
            memory_decay_profile=profile.memory_decay_profile if profile else None,
            engine_params=profile.engine_params if profile else None,
            memory_shared_context_ids=memory_shared_context_ids,
        )

        agent = AgentFactory.create_general_agent(params)
        agent.approval_session_key = f"kanban:{task.task_id}"

        try:
            acc = _StreamAccumulator()

            async def _open_stream(query_input: object):
                async for event in agent.process_stream(
                    query=query_input,
                    chat_history=None,
                    chat_id=task.task_id,
                ):
                    if isinstance(event, dict):
                        yield event

            from app.services.agent.fission_config import max_parallel_from_engine_params
            from app.services.agent.swarm_fission_resume import stream_with_swarm_fission_resume

            async for event in stream_with_swarm_fission_resume(
                agent,
                context,
                _open_stream,
                max_concurrent=max_parallel_from_engine_params(profile.engine_params if profile else None),
            ):
                acc.add(event)

            return acc.to_result()
        finally:
            await agent.close()
