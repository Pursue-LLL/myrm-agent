"""Stream lane factories — dynamic workflow, deep research, and fast lane SSE builders."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterable
from typing import cast

from fastapi.responses import JSONResponse
from myrm_agent_harness.utils.runtime.cancellation import CancellationToken

from app.ai_agents import AgentFactory, GeneralAgentParams
from app.core.types import ModelConfig
from app.core.utils.delivery_provenance import apply_general_agent_pipeline_banner
from app.services.agent.params import ArchiveRestoreRequestError, _extract_text_from_query
from app.services.agent.params.models import MultimodalQuery
from app.services.agent.streaming import ai_deep_research_service_stream

logger = logging.getLogger(__name__)


def archive_restore_error_response(exc: ArchiveRestoreRequestError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "detail": str(exc),
            "error_code": "archive_restore_action_invalid",
        },
    )


def _inject_wu_consumed(chunk: dict[str, object]) -> None:
    """Attach ``wu_consumed`` to a MESSAGE_END chunk for Sandbox deployments."""
    from app.config.deploy_mode import is_sandbox

    if not is_sandbox():
        return
    cost_usd = chunk.get("cost_usd")
    if not isinstance(cost_usd, int | float) or cost_usd <= 0:
        return
    from app.config.settings import get_settings

    wu_per_usd = get_settings().control_plane.platform_wu_per_usd
    chunk["wu_consumed"] = max(1, int(float(cost_usd) * wu_per_usd))


async def create_dynamic_workflow_stream(
    params: GeneralAgentParams,
    cancel_token: "CancellationToken | None",
    resume_value: dict[str, object] | None = None,
) -> AsyncIterable[dict[str, object]]:
    """Build Dynamic Workflow SSE stream from GeneralAgentParams.

    Creates a full GeneralAgent (same as the normal agent path) so that
    sub-agents spawned by the DW engine inherit the complete tool registry,
    catalog, budget, and security policies.
    """
    from myrm_agent_harness.agent.dynamic_workflow import (
        WorkflowPlanReview,
        run_dynamic_workflow_stream,
    )
    from myrm_agent_harness.api import AgentEventType
    from myrm_agent_harness.utils.token_economics.tracker import (
        get_token_tracker,
        init_token_tracker,
        reset_token_tracker,
    )

    from app.ai_agents.subagent_catalog import DatabaseSubagentCatalog
    from app.core.utils.chat_utils import convert_chat_history
    from app.services.budget.enforcer import (
        reset_session_budget,
        should_block_execution,
    )

    if await should_block_execution():
        yield {"type": AgentEventType.MESSAGE.value, "messageId": params.message_id or "", "data": ""}
        yield {"type": AgentEventType.MESSAGE_END.value, "messageId": params.message_id or "", "usage": {}, "completion_status": "budget_blocked"}
        return

    reset_session_budget(chat_id=params.chat_id)

    from app.ai_agents.general_agent.factory import build_general_agent

    agent_wrapper = AgentFactory.create_general_agent(params)
    effective_chat_id = params.chat_id or agent_wrapper.chat_id or "default"
    base_agent = await build_general_agent(agent_wrapper, effective_chat_id)

    history = await convert_chat_history(params.chat_history) if params.chat_history else []

    catalog = DatabaseSubagentCatalog(
        bound_agent_ids=list(params.subagent_ids or []),
    )

    raw_q = params.query
    if isinstance(raw_q, str):
        text_query = raw_q
    elif isinstance(raw_q, list):
        text_query = _extract_text_from_query(cast(MultimodalQuery, raw_q))
    else:
        text_query = str(raw_q)

    init_token_tracker()

    message_id = params.message_id or "default_msg"

    async def _dw_approval_gate(review: WorkflowPlanReview) -> bool:
        from app.services.agent.streaming import PhaseWaiter

        plan_key = f"plan:{message_id}"
        waiter = PhaseWaiter.register(plan_key)
        logger.info(
            "Dynamic Workflow plan confirmation waiting: message_id=%s spawn_count=%s",
            message_id,
            review.spawn_count,
        )
        answer = await waiter.wait_for_answer()
        if answer is False:
            return False
        if answer is None:
            return False
        return True

    try:
        async for chunk in run_dynamic_workflow_stream(
            parent_agent=base_agent,
            query=text_query,
            chat_history=history,
            chat_id=params.chat_id or "default_chat",
            message_id=message_id,
            cancel_token=cancel_token,
            catalog=catalog,
            approval_gate=_dw_approval_gate,
            resume_value=resume_value,
        ):
            if isinstance(chunk, dict) and chunk.get("type") == "message_end":
                tracker = get_token_tracker()
                if tracker:
                    chunk["usage"] = tracker.usage.to_dict() if hasattr(tracker.usage, "to_dict") else {}
                    chunk["cost_usd"] = round(tracker.total_cost_usd, 6)
                    _inject_wu_consumed(chunk)
            yield chunk
    finally:
        reset_token_tracker()


async def create_deep_research_stream(
    params: GeneralAgentParams,
    cancel_token: "CancellationToken | None",
    research_model_cfg: "ModelConfig | None" = None,
) -> AsyncIterable[dict[str, object]]:
    """Build Deep Research SSE stream from GeneralAgentParams.

    Extracts the LLM and search tools from the resolved params,
    then delegates to ai_deep_research_service_stream.
    If research_model_cfg is provided, it is used for research sub-agents
    (lighter/cheaper model for search tasks), while the main LLM handles
    planning and report generation.
    """
    from myrm_agent_harness.toolkits import create_web_search_tool
    from myrm_agent_harness.toolkits.llms import llm_manager

    from app.core.utils.chat_utils import convert_chat_history

    llm = await llm_manager.get_llm_from_config(params.model_cfg, api_keys=getattr(params.model_cfg, "api_keys", None))
    search_tool = create_web_search_tool(search_service_cfg=params.search_service_cfg)

    research_agent_llm = None
    if research_model_cfg:
        try:
            research_agent_llm = await llm_manager.get_llm_from_config(
                research_model_cfg,
                api_keys=getattr(research_model_cfg, "api_keys", None),
            )
        except Exception:
            logger.warning("Failed to create research agent LLM, falling back to main LLM")

    raw_q = params.query
    if isinstance(raw_q, str) or isinstance(raw_q, list):
        text_query = _extract_text_from_query(cast(MultimodalQuery, raw_q))
    else:
        text_query = ""
    if text_query:
        text_query = cast(
            str,
            apply_general_agent_pipeline_banner(text_query, channel_name=params.channel_name),
        )
    chat_history = await convert_chat_history(params.chat_history) if params.chat_history else None

    on_report_ready = _build_wiki_vault_callback(params) if params.enable_wiki else None
    on_explore = _build_explore_callback(params) if params.enable_wiki else None

    async for chunk in ai_deep_research_service_stream(
        llm=llm,
        query=text_query,
        message_id=params.message_id or "",
        chat_history=chat_history,
        parent_tools=[search_tool],
        cancel_token=cancel_token,
        context={
            "session_id": params.chat_id or "",
            "agent_id": params.agent_id or "",
        },
        research_agent_llm=research_agent_llm,
        on_report_ready=on_report_ready,
        on_explore=on_explore,
    ):
        yield chunk


_EXPLORE_MAX_ARTICLES = 8
_EXPLORE_CHAR_BUDGET = 6000


def _build_explore_callback(params: GeneralAgentParams):
    """Build an on_explore callback that searches the local Wiki for relevant knowledge.

    Uses FTS5 full-text search only (zero LLM calls, zero cost).
    Returns a formatted summary of local articles related to the research plan,
    so the orchestrator can skip redundant web searches.
    """

    async def _explore_local_knowledge(research_plan: str) -> str | None:
        from myrm_agent_harness.toolkits.wiki.core.structure import WikiStructure
        from myrm_agent_harness.toolkits.wiki.retrieval.indexer import WikiIndexer

        from app.services.wiki.vault_resolver import resolve_wiki_vault_path

        wiki_base_dir = resolve_wiki_vault_path(params.agent_id)
        if not wiki_base_dir.exists():
            return None

        structure = WikiStructure(wiki_base_dir)
        indexer = WikiIndexer(structure)

        results = await indexer.search(research_plan, limit=_EXPLORE_MAX_ARTICLES)
        if not results:
            return None

        sections: list[str] = []
        total_chars = 0
        for concept_name, score in results:
            if total_chars >= _EXPLORE_CHAR_BUDGET:
                break
            concept_path = structure.get_concept_file_path(concept_name)
            if not concept_path.exists():
                continue
            content = concept_path.read_text(encoding="utf-8")
            remaining = _EXPLORE_CHAR_BUDGET - total_chars
            if len(content) > remaining:
                content = content[:remaining] + "\n[truncated]"
            sections.append(f"### {concept_name} (relevance: {score:.2f})\n\n{content}")
            total_chars += len(content)

        if not sections:
            return None

        logger.info(
            "[deep-research-explore] Found %d local articles (%d chars)",
            len(sections),
            total_chars,
        )
        return "\n\n---\n\n".join(sections)

    return _explore_local_knowledge


def _build_wiki_vault_callback(params: GeneralAgentParams):
    """Build an on_report_ready callback that vaults Deep Research results into wiki.

    Each structured agent_result is written as a separate raw markdown file
    into the wiki ingestion directory, then enqueued for background compilation.
    """
    from pathlib import Path

    async def _vault_research_to_wiki(result: object) -> None:
        from datetime import UTC, datetime

        from myrm_agent_harness.toolkits.llms import llm_manager
        from myrm_agent_harness.toolkits.wiki.core.structure import WikiStructure

        from app.services.wiki.vault_resolver import resolve_wiki_vault_path

        wiki_base_dir = resolve_wiki_vault_path(params.agent_id)
        wiki_base_dir.mkdir(parents=True, exist_ok=True)

        agent_results = getattr(result, "agent_results", [])
        if not agent_results:
            return

        complete_results = [r for r in agent_results if not r.get("partial")]
        if not complete_results:
            return

        structure = WikiStructure(wiki_base_dir)
        structure.ensure_structure()

        from myrm_agent_harness.toolkits.wiki.pipeline.raw_gate import (
            RawConflictPolicy,
            RawPublishRequest,
            publish_raw,
        )

        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        written_files: list[Path] = []

        for idx, entry in enumerate(complete_results):
            task = entry.get("task", "research")
            content = entry.get("result", "")
            if not content or len(content) < 200:
                continue

            safe_task = "".join(c if c.isalnum() or c in "-_" else "_" for c in task[:60]).strip("_")
            relative_path = f"deep_research_{timestamp}_{idx}_{safe_task}.md"

            escaped_task = task.replace('"', '\\"')
            frontmatter = (
                f"---\n"
                f"source: deep_research\n"
                f"bridge_source: deep_research\n"
                f"task: \"{escaped_task}\"\n"
                f"timestamp: \"{timestamp}\"\n"
                f"session_id: \"{params.chat_id or ''}\"\n"
                f"---\n\n"
            )
            result = await publish_raw(
                structure,
                RawPublishRequest(
                    relative_path=relative_path,
                    content=frontmatter + content,
                    conflict_policy=RawConflictPolicy.FAIL,
                ),
                caller="chat",
            )
            if result.security_blocked:
                logger.warning(
                    "[deep-research-vault] Blocked raw write for %s: sensitive content",
                    relative_path,
                )
                continue
            if result.written:
                written_files.append(result.absolute_path)

        if not written_files:
            return

        try:
            from app.services.wiki.vault_service import get_wiki_archiver

            wiki_llm = await llm_manager.get_llm_from_config(
                params.model_cfg, api_keys=getattr(params.model_cfg, "api_keys", None)
            )
            archiver = get_wiki_archiver(wiki_llm, agent_id=params.agent_id)
            for fp in written_files:
                archiver._compiler.enqueue_file(fp)
            logger.info(
                "[deep-research-vault] Enqueued %d research files for wiki compilation",
                len(written_files),
            )
        except Exception as e:
            logger.warning("[deep-research-vault] Failed to enqueue for compilation: %s", e)

    return _vault_research_to_wiki


async def create_fast_lane_stream(
    params: GeneralAgentParams,
    cancel_token: "CancellationToken | None",
) -> AsyncIterable[dict[str, object]]:
    """Build Fast Lane SSE stream for SIMPLE routing tier.

    Bypasses the heavy AgentFactory and LangGraph engine entirely.
    Uses a bare-bones LLM chain with 0 tools and a minimal system prompt.
    """
    from langchain_core.messages import HumanMessage, SystemMessage
    from myrm_agent_harness.api import AgentEventType
    from myrm_agent_harness.toolkits.llms import llm_manager

    from app.core.utils.chat_utils import convert_chat_history

    llm = await llm_manager.get_llm_from_config(params.model_cfg, api_keys=getattr(params.model_cfg, "api_keys", None))

    system_prompt = "你是一个友好的AI助手，请简短、自然地回应用户的问候或简单对话。"
    if params.user_instructions:
        system_prompt += f"\n\n用户指令:\n{params.user_instructions}"

    messages = [SystemMessage(content=system_prompt)]

    if params.chat_history:
        history = await convert_chat_history(params.chat_history)
        messages.extend(history)

    if isinstance(params.query, str):
        messages.append(
            HumanMessage(
                content=cast(
                    str,
                    apply_general_agent_pipeline_banner(params.query, channel_name=params.channel_name),
                ),
            ),
        )
    else:
        wrapped = apply_general_agent_pipeline_banner(
            cast(MultimodalQuery, params.query),
            channel_name=params.channel_name,
        )
        if isinstance(wrapped, str):
            messages.append(HumanMessage(content=wrapped))
        else:
            text_query = _extract_text_from_query(cast(MultimodalQuery, wrapped))
            messages.append(
                HumanMessage(
                    content=cast(
                        str,
                        apply_general_agent_pipeline_banner(
                            text_query,
                            channel_name=params.channel_name,
                        ),
                    ),
                ),
            )

    yield {
        "type": AgentEventType.STATUS.value,
        "messageId": params.message_id or "",
        "data": {"status": "fast_lane_active"},
    }

    try:
        # Enable stream_usage for token tracking if supported by the provider
        stream_kwargs = {}
        if hasattr(llm, "bind_tools"):  # A simple heuristic to check if it's a modern chat model
            stream_kwargs["stream_usage"] = True

        async for chunk in llm.astream(messages, **stream_kwargs):
            if cancel_token and cancel_token.is_cancelled:
                break
            if chunk.content:
                yield {
                    "type": AgentEventType.MESSAGE.value,
                    "messageId": params.message_id or "",
                    "data": chunk.content,
                }

            # Extract usage metadata from the final chunk
            if hasattr(chunk, "usage_metadata") and chunk.usage_metadata:
                usage = chunk.usage_metadata
                yield {
                    "type": AgentEventType.TOKEN_USAGE.value,
                    "messageId": params.message_id or "",
                    "data": {
                        "prompt_tokens": usage.get("input_tokens", 0),
                        "completion_tokens": usage.get("output_tokens", 0),
                        "total_tokens": usage.get("total_tokens", 0),
                    },
                }

        yield {
            "type": AgentEventType.MESSAGE_END.value,
            "messageId": params.message_id or "",
            "usage": {},
            "completion_status": "success",
        }
    except Exception as e:
        logger.error(f"Fast Lane LLM error: {e}", exc_info=True)
        raise
