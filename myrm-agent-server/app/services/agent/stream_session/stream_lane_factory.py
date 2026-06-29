"""Stream lane factories — dynamic workflow, deep research, fast lane, and consensus SSE builders."""

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


def _cfg_float(cfg: dict[str, object], key: str, default: float) -> float:
    """Read a numeric config value as float, falling back to ``default``."""
    value = cfg.get(key)
    return float(value) if isinstance(value, int | float | str) else default


def _cfg_int(cfg: dict[str, object], key: str, default: int) -> int:
    """Read a numeric config value as int, falling back to ``default``."""
    value = cfg.get(key)
    return int(value) if isinstance(value, int | float | str) else default


async def create_dynamic_workflow_stream(
    params: GeneralAgentParams,
    cancel_token: "CancellationToken | None",
) -> AsyncIterable[dict[str, object]]:
    """Build Dynamic Workflow SSE stream from GeneralAgentParams.

    Creates a full GeneralAgent (same as the normal agent path) so that
    sub-agents spawned by the DW engine inherit the complete tool registry,
    catalog, budget, and security policies.
    """
    from myrm_agent_harness.agent.dynamic_workflow import run_dynamic_workflow_stream
    from myrm_agent_harness.agent.streaming.types import AgentEventType
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
    try:
        async for chunk in run_dynamic_workflow_stream(
            parent_agent=base_agent,
            query=text_query,
            chat_history=history,
            chat_id=params.chat_id or "default_chat",
            message_id=params.message_id or "default_msg",
            cancel_token=cancel_token,
            catalog=catalog,
        ):
            if isinstance(chunk, dict) and chunk.get("type") == "message_end":
                tracker = get_token_tracker()
                if tracker:
                    chunk["usage"] = tracker.usage.to_dict() if hasattr(tracker.usage, "to_dict") else {}
                    chunk["cost_usd"] = round(tracker.total_cost_usd, 6)
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

    async for chunk in ai_deep_research_service_stream(
        llm=llm,
        query=text_query,
        message_id=params.message_id or "",
        chat_history=chat_history,
        parent_tools=[search_tool],
        cancel_token=cancel_token,
        context={
            "session_id": params.chat_id or "",
        },
        research_agent_llm=research_agent_llm,
    ):
        yield chunk


async def create_fast_lane_stream(
    params: GeneralAgentParams,
    cancel_token: "CancellationToken | None",
) -> AsyncIterable[dict[str, object]]:
    """Build Fast Lane SSE stream for SIMPLE routing tier.

    Bypasses the heavy AgentFactory and LangGraph engine entirely.
    Uses a bare-bones LLM chain with 0 tools and a minimal system prompt.
    """
    from langchain_core.messages import HumanMessage, SystemMessage
    from myrm_agent_harness.agent.streaming.types import AgentEventType
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


async def create_consensus_stream(
    params: GeneralAgentParams,
    cancel_token: "CancellationToken | None",
    consensus_cfg: dict[str, object] | None = None,
    reference_model_cfgs: "list[object] | None" = None,
    aggregator_model_cfg: object | None = None,
) -> AsyncIterable[dict[str, object]]:
    """Build MoA (Mixture-of-Agents) consensus SSE stream.

    Pre-resolved ``ModelConfig`` objects are passed from the orchestrator
    for reference and aggregator models.  Falls back to the main LLM
    when specific models are unavailable.
    """
    from myrm_agent_harness.agent.streaming.types import AgentEventType
    from myrm_agent_harness.toolkits.llms import llm_manager
    from myrm_agent_harness.toolkits.llms.consensus import (
        ConsensusConfig,
        ConsensusEngine,
        ConsensusStreamEvent,
    )
    from myrm_agent_harness.utils.token_economics.tracker import (
        get_token_tracker,
        init_token_tracker,
        reset_token_tracker,
    )

    cfg = consensus_cfg or {}

    main_llm = await llm_manager.get_llm_from_config(
        params.model_cfg,
        api_keys=getattr(params.model_cfg, "api_keys", None),
    )

    reference_llms = []
    for mc in reference_model_cfgs or []:
        try:
            llm = await llm_manager.get_llm_from_config(mc, api_keys=getattr(mc, "api_keys", None))
            reference_llms.append(llm)
        except Exception:
            logger.warning(
                "Consensus: failed to create reference LLM for %s, skipping",
                getattr(mc, "model", "?"),
            )

    if not reference_llms:
        reference_llms = [main_llm]

    if aggregator_model_cfg:
        try:
            aggregator_llm = await llm_manager.get_llm_from_config(
                aggregator_model_cfg,
                api_keys=getattr(aggregator_model_cfg, "api_keys", None),
            )
        except Exception:
            logger.warning("Consensus: aggregator unavailable, using main LLM")
            aggregator_llm = main_llm
    else:
        aggregator_llm = main_llm

    consensus_config = ConsensusConfig(
        reference_temperature=_cfg_float(cfg, "reference_temperature", 0.6),
        aggregator_temperature=_cfg_float(cfg, "aggregator_temperature", 0.4),
        min_successful=_cfg_int(cfg, "min_successful", 1),
        timeout_per_model=_cfg_float(cfg, "timeout_per_model", 120.0),
        timeout_total=_cfg_float(cfg, "timeout_total", 300.0),
    )

    engine = ConsensusEngine(
        reference_llms=reference_llms,
        aggregator_llm=aggregator_llm,
        config=consensus_config,
    )

    ref_model_names = [
        next(
            (v for attr in ("model_name", "model", "name") if (v := getattr(llm, attr, None)) and isinstance(v, str)),
            type(llm).__name__,
        )
        for llm in reference_llms
    ]

    msg_id = params.message_id or ""

    yield {
        "type": AgentEventType.STATUS.value,
        "messageId": msg_id,
        "step_key": "consensus_active",
        "data": {"reference_models": ref_model_names},
    }

    raw_q = params.query
    if isinstance(raw_q, str):
        text_query = raw_q
    elif isinstance(raw_q, list):
        text_query = _extract_text_from_query(cast(MultimodalQuery, raw_q))
    else:
        text_query = str(raw_q)

    final_result: ConsensusStreamEvent | None = None

    # Bracket the engine run with a request-scoped token tracker. The LLM
    # adapter records each reference + aggregator call's tokens and cost into
    # this tracker on its streaming path. Consensus bypasses the agent runtime
    # that normally owns the tracker lifecycle, so without this the product's
    # most expensive feature would report zero cost.
    init_token_tracker()
    try:
        async for event in engine.run_stream(
            text_query,
            system_prompt=params.user_instructions,
            cancel_token=cancel_token,
        ):
            if cancel_token and cancel_token.is_cancelled:
                return

            if event.kind == "ref_done" and event.ref:
                yield {
                    "type": AgentEventType.STATUS.value,
                    "messageId": msg_id,
                    "step_key": "consensus_reference_done",
                    "data": {
                        "model": event.ref.model,
                        "success": event.ref.success,
                        "elapsed": event.ref.elapsed_seconds,
                        "content": event.ref.content if event.ref.success else None,
                    },
                }
            elif event.kind == "agg_chunk" and event.chunk:
                yield {
                    "type": AgentEventType.MESSAGE.value,
                    "messageId": msg_id,
                    "data": event.chunk,
                }
            elif event.kind == "done":
                final_result = event

        if cancel_token and cancel_token.is_cancelled:
            return

        result = final_result.result if final_result else None
        if result and not result.success:
            yield {
                "type": AgentEventType.MESSAGE.value,
                "messageId": msg_id,
                "data": f"Consensus failed: {result.error}",
            }

        tracker = get_token_tracker()
        yield {
            "type": AgentEventType.MESSAGE_END.value,
            "messageId": msg_id,
            "usage": tracker.usage.to_dict() if tracker else {},
            "token_economics": tracker.to_dict() if tracker else {},
            "cost_usd": round(tracker.total_cost_usd, 6) if tracker else 0.0,
            "cost_status": tracker.cost_status if tracker else "unknown",
            "model": result.aggregator_model if result else "",
            "completion_status": "success" if (result and result.success) else "error",
            "consensus_meta": {
                "models_used": len(result.reference_responses) if result else 0,
                "models_succeeded": (sum(1 for r in result.reference_responses if r.success) if result else 0),
                "aggregator_model": result.aggregator_model if result else "",
                "elapsed_seconds": result.elapsed_seconds if result else 0,
            },
        }
    finally:
        reset_token_tracker()
