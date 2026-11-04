"""[INPUT]
- app.services.agent.params.models::AgentRequest, MultimodalQuery (POS: Agent API request DTO)
- app.services.agent.params.mention (POS: @-mention reference materialization)
- app.services.agent.params.upload_sync (POS: uploaded file workspace sync)
- app.services.agent.params.archive_restore (POS: typed archive restore materialization)
- app.services.chat.context_bomb_guard (POS: oversized prompt spillover)

[OUTPUT]
- EnrichedQuery: final query text/parts plus mention warnings, restore results, JIT subagents
- enrich_query(): append every server-side context block to the user query before execution

[POS]
Query enrichment stage of Agent request conversion. All context that must reach the model as part
of the user message (not the system prompt, to keep the prompt cache prefix stable) lands here.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from app.core.types import ModelConfig

from .archive_restore import (
    build_archive_restore_action_context_with_results,
    inject_archive_restore_actions_into_query,
)
from .chat_context import ChatContext
from .mention import (
    _MENTION_PRIOR_CHAT_FALLBACK_WORKSPACE,
    _build_mention_reference_context,
    _inject_mentioned_files_into_query,
)
from .models import AgentRequest, MultimodalQuery
from .upload_sync import (
    inject_uploaded_files_into_query,
    sync_uploaded_files_to_workspace,
)

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class EnrichedQuery:
    """User query after every server-side context block has been appended."""

    query: MultimodalQuery
    mention_warnings: list[str] = field(default_factory=list)
    archive_restore_results: list[dict[str, object]] = field(default_factory=list)
    jit_subagents: dict[str, object] | None = None


async def enrich_query(request: AgentRequest, context: ChatContext, model_cfg: ModelConfig | None) -> EnrichedQuery:
    """Materialize mentions, uploaded files, restore actions, @agent directives and spillover."""

    final_query = request.query
    mention_warnings: list[str] = []
    archive_restore_results: list[dict[str, object]] = []
    jit_subagents = context.jit_subagents

    restore_materialization = await build_archive_restore_action_context_with_results(
        request,
        context.chat_workspace_dir,
    )
    restore_ctx = restore_materialization.prompt_context
    if restore_ctx:
        final_query = inject_archive_restore_actions_into_query(final_query, restore_ctx)
    mention_warnings.extend(restore_materialization.warnings)
    archive_restore_results.extend(restore_materialization.results)

    if request.mention_references:
        max_ctx_tokens = model_cfg.max_context_tokens if model_cfg else None
        prior_chat_refs = [ref for ref in request.mention_references if ref.type == "prior_chat"]
        workspace_refs = [ref for ref in request.mention_references if ref.type != "prior_chat"]
        if workspace_refs and not context.chat_workspace_dir:
            mention_warnings.append("Workspace unavailable; file and workspace references were skipped")
        refs_to_inject = [
            *prior_chat_refs,
            *(workspace_refs if context.chat_workspace_dir else []),
        ]
        if refs_to_inject:
            mention_workspace_dir = context.chat_workspace_dir or _MENTION_PRIOR_CHAT_FALLBACK_WORKSPACE
            mention_ctx, mention_context_warnings, mention_tokens = await _build_mention_reference_context(
                refs_to_inject,
                mention_workspace_dir,
                max_ctx_tokens,
                request.agent_id,
            )
            mention_warnings.extend(mention_context_warnings)
            if mention_ctx:
                final_query = _inject_mentioned_files_into_query(final_query, mention_ctx)
                logger.info(
                    "Injected %d context references (%d tokens, %d warnings)",
                    len(refs_to_inject),
                    mention_tokens,
                    len(mention_warnings),
                )

    if request.uploaded_file_ids and context.chat_workspace_dir:
        try:
            synced = await sync_uploaded_files_to_workspace(request.uploaded_file_ids, context.chat_workspace_dir)
            if synced:
                final_query = inject_uploaded_files_into_query(final_query, synced, workspace_dir=context.chat_workspace_dir)
                logger.info("Synced %d uploaded files to workspace", len(synced))
        except Exception:
            logger.warning("Failed to sync uploaded files to workspace", exc_info=True)

    if request.mentioned_agent_ids:
        try:
            from app.services.agent.agent_service import AgentService

            mentioned_names = []
            if jit_subagents is None:
                jit_subagents = {}

            for aid in request.mentioned_agent_ids:
                agent = await AgentService.get_agent_by_id(aid)
                if agent and agent.display_name:
                    mentioned_names.append(agent.display_name)
                    # Add to jit_subagents so the main agent gets the delegate_task tool
                    jit_subagents[aid] = {
                        "name": agent.display_name,
                        "description": agent.description or "Mentioned agent",
                        "agent_id": aid,
                    }

            if mentioned_names:
                names_str = ", ".join(mentioned_names)
                directive = (
                    f"\n\n[System Directive: 用户显式要求了以下专家参与本次任务：{names_str}。"
                    "你必须使用 delegate_task 工具将相关工作委派给他们，严禁你自己直接执行他们的专业工作！"
                    "请根据用户的自然语言逻辑安排他们的执行顺序。]"
                )
                if isinstance(final_query, str):
                    final_query = f"{final_query}{directive}"
                elif isinstance(final_query, list):
                    next_query = list(final_query)
                    next_query.append({"type": "text", "text": directive})
                    final_query = next_query
        except Exception as e:
            logger.warning("Failed to inject mentioned agents directive: %s", e)

    from app.core.channel_bridge.learn_handler import (
        rewrite_learn_query_if_needed,
    )

    final_query = rewrite_learn_query_if_needed(final_query)

    from app.services.chat.context_bomb_guard import ContextBombDefenseService

    # A long text of a turn with attachments (a plain text query was parked at the stream entry): parked in a
    # workspace file the same way the stored message is, so the stub of the live turn and of the history agree.
    # The write is blocking I/O: keep it off the event loop.
    final_query, parked = await asyncio.to_thread(
        ContextBombDefenseService.guard_and_spill_query, final_query, context.chat_workspace_dir
    )
    if parked.is_spilled:
        logger.info(
            "ContextBombGuard parked query for chat_id=%s: chars=%d path=%s sha256=%s",
            request.chat_id,
            parked.original_char_count,
            parked.relative_path,
            parked.content_sha256,
        )
    # Background sweep of stale transient spill files (>24h)
    try:
        ContextBombDefenseService.sweep_stale_spillover_files(context.chat_workspace_dir)
    except OSError:
        logger.debug("Sweep of stale spill files failed for chat_id=%s", request.chat_id, exc_info=True)

    return EnrichedQuery(
        query=final_query,
        mention_warnings=mention_warnings,
        archive_restore_results=archive_restore_results,
        jit_subagents=jit_subagents,
    )
