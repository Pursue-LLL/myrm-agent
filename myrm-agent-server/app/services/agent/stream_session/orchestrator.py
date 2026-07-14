"""Agent stream session orchestrator — business flow for General Agent SSE.

[INPUT]
- app.services.agent.params (POS: request conversion)
- app.services.agent.stream_session.stream_generator (POS: SSE generation)

[OUTPUT]
- run_agent_stream: full orchestration returning StreamingResponse | JSONResponse

[POS]
Service-layer stream orchestration. HTTP route decorators remain in api/agents/general_agent/streaming.py.
"""

import logging

from fastapi import Request
from fastapi.responses import JSONResponse, StreamingResponse
from myrm_agent_harness.agent.middlewares.approval.scheduler import (
    ApprovalTimeoutScheduler,
)
from myrm_agent_harness.utils.runtime.cancellation import (
    CancellationMonitor,
    CancellationRegistry,
    CancellationToken,
)
from myrm_agent_harness.utils.runtime.steering import SteeringToken

from app.core.types import ModelConfig
from app.services.agent.params import (
    AgentRequest,
    ArchiveRestoreRequestError,
    ModelSelection,
    _extract_text_from_query,
    _resolve_model_config,
    convert_to_general_agent_params,
    prevalidate_archive_restore_actions,
)
from app.services.agent.steering_registry import SteeringRegistry
from app.services.agent.stream_session.reconnect import try_stream_reconnect
from app.services.agent.stream_session.risk_gate import check_stream_risk
from app.services.agent.stream_session.stream_generator import (
    AgentStreamSession,
    build_disconnect_checker,
    launch_buffered_stream,
)
from app.services.agent.stream_session.stream_lane_factory import archive_restore_error_response
from app.services.agent.streaming_support.stream_collector import StreamContentCollector

logger = logging.getLogger(__name__)

_ACTION_MODE_FEATURE_GATE: dict[str, str] = {
    "deep_research": "deep_research",
    "consensus": "consensus",
}

_SEARCH_AGENT_IDS: frozenset[str] = frozenset({"builtin-fast-search", "builtin-deep-search"})

# Gateway hygiene limit: ~120K tokens (rough character-to-token ratio) to prevent OOM
_GATEWAY_MAX_INPUT_CHARS: int = 360_000


async def run_agent_stream(
    request: AgentRequest,
    http_request: Request,
) -> StreamingResponse | JSONResponse:
    """Streaming Agent execution with gateway lifecycle management.

    Backend is the authoritative store: persists user message first,
    then loads chat history from DB (frontend no longer sends chat_history).
    """
    async for _ in http_request.stream():
        pass

    from myrm_agent_harness.agent.streaming.stream_buffer import GlobalStreamRegistry

    registry = GlobalStreamRegistry.get()
    reconnect_response = await try_stream_reconnect(request, http_request)
    if reconnect_response is not None:
        return reconnect_response

    gated_feature = _ACTION_MODE_FEATURE_GATE.get(request.action_mode or "")
    if gated_feature:
        from myrm_agent_harness.core.features import get_features

        if not get_features().enabled(gated_feature):
            return JSONResponse(
                status_code=403,
                content={"detail": f"{request.action_mode} is disabled via Feature Gate"},
            )

    text_content = _extract_text_from_query(request.query) if request.resume_value is None else ""

    # Gateway hygiene check: block massive malicious payloads before they hit the agent harness
    if len(text_content) > _GATEWAY_MAX_INPUT_CHARS:
        logger.warning(f"Gateway rejected massive payload: length={len(text_content)} chars")
        return JSONResponse(
            status_code=400,
            content={
                "detail": "Request exceeds gateway token limits (approx 120K tokens). Please reduce the size of your input."
            },
        )

    if request.resume_value is None:
        risk_block = await check_stream_risk(text_content, request.chat_id)
        if risk_block is not None:
            return risk_block
        try:
            await prevalidate_archive_restore_actions(request)
        except ArchiveRestoreRequestError as exc:
            return archive_restore_error_response(exc)

    chat_history: list[list[str | dict[str, object]]] = []
    if request.chat_id:
        from app.platform_utils import get_session_factory
        from app.services.chat.chat_service import ChatService

        session_factory = get_session_factory()
        async with session_factory() as db:
            is_regenerate = request.sibling_group_id is not None
            if request.resume_value is None and not is_regenerate:
                from datetime import datetime
                from datetime import timezone as tz_module

                if request.timestamp is not None:
                    sent_at_utc = datetime.fromtimestamp(request.timestamp, tz=tz_module.utc)
                else:
                    sent_at_utc = datetime.now(tz=tz_module.utc)

                sent_timezone = request.timezone or "UTC"

                extra_data_val = None
                if request.resume_value is None and isinstance(request.query, list):
                    extra_data_val = {"original_query": request.query}

                msg = await ChatService.ensure_chat_and_append_user_message(
                    chat_id=request.chat_id,
                    content=text_content,
                    sent_at=sent_at_utc,
                    sent_timezone=sent_timezone,
                    message_id=request.message_id,
                    action_mode=request.action_mode,
                    agent_id=request.agent_id or "default",
                    ephemeral_subagents=request.ephemeral_subagents,
                    extra_data=extra_data_val,
                    is_incognito=request.incognito_mode,
                )
                chat_history = await ChatService.load_web_chat_history(
                    request.chat_id,
                    exclude_message_id=msg.id,
                    api_key=None,
                )
            else:
                chat_history = await ChatService.load_web_chat_history(request.chat_id, api_key=None)
            await db.commit()

    extra_context: dict[str, object] | None = None
    try:
        if request.resume_value is not None:
            from langgraph.types import Command

            if request.chat_id:
                if not ApprovalTimeoutScheduler.get().resolve_if_first(request.chat_id):
                    logger.warning(
                        "Resume rejected (timeout already resolved): chat_id=%s",
                        request.chat_id,
                    )
                    return JSONResponse(
                        status_code=409,
                        content={"detail": "This approval has already been resolved by timeout."},
                    )

            logger.info(f"🔄 Resume 模式: chat_id={request.chat_id}, decision={request.resume_value.get('decision')}")
            params, routing_tier, context_warnings, archive_restore_results = await convert_to_general_agent_params(
                request,
                chat_history,
                http_request=http_request,
            )
            params.query = Command(resume=request.resume_value)

            extra_context = {"hitl_session_active": True}
            logger.info("⏸️ HITL Session marked active for cache preservation")
        else:
            params, routing_tier, context_warnings, archive_restore_results = await convert_to_general_agent_params(
                request,
                chat_history,
                http_request=http_request,
            )
    except ArchiveRestoreRequestError as exc:
        return archive_restore_error_response(exc)

    research_model_cfg: ModelConfig | None = None
    if request.action_mode == "deep_research" and request.light_model_selection:
        try:
            from app.core.channel_bridge.config_loader import load_user_configs

            configs = await load_user_configs()
            providers_dict = configs.providers_dict if configs else None
            if request.light_model_selection is not None:
                research_model_cfg = await _resolve_model_config(request.light_model_selection, providers_dict)
        except Exception:
            logger.warning("Failed to resolve research model")

    if request.action_mode == "deep_research" and not params.enable_web_search:
        return JSONResponse(
            status_code=422,
            content={"detail": "Search service not configured. Deep Research requires a configured search service."},
        )

    if request.agent_id in _SEARCH_AGENT_IDS and not params.enable_web_search:
        return JSONResponse(
            status_code=422,
            content={"detail": "Search service not configured. Please add a search service in Settings."},
        )

    cancel_token = CancellationToken(request_id=request.message_id)
    CancellationRegistry.register(cancel_token)

    steering_token = SteeringToken() if request.chat_id else None
    if steering_token and request.chat_id:
        SteeringRegistry.register(request.chat_id, steering_token)

    from app.services.agent.goal_registry import (
        GoalRegistry,
        check_and_handle_branch_stash,
    )

    goal_provider = None
    if request.chat_id:
        await check_and_handle_branch_stash(request.chat_id)
        goal_provider = GoalRegistry.get_or_create_provider(request.chat_id)
        if request.goal:
            from myrm_agent_harness.agent.goals.types import GoalBudget

            budget = GoalBudget(
                max_tokens=request.goal.max_tokens,
                max_usd=request.goal.max_usd,
                max_time_seconds=request.goal.max_time_seconds,
                max_turns=request.goal.max_turns,
                convergence_window=request.goal.convergence_window,
                loop_on_pause=request.goal.loop_on_pause,
                max_loop_restarts=request.goal.max_loop_restarts,
            )
            acceptance_criteria = request.goal.acceptance_criteria
            ui_summary = request.goal.ui_summary
            constraints = request.goal.constraints
            protected_paths = request.goal.protected_paths
            active_goal = await goal_provider.get_active_goal(request.chat_id)
            if not active_goal:
                await goal_provider.create_goal(
                    session_id=request.chat_id,
                    objective="User requested goal",
                    budget=budget,
                    acceptance_criteria=acceptance_criteria,
                    constraints=constraints,
                    protected_paths=protected_paths,
                    ui_summary=ui_summary,
                )
            else:
                await goal_provider.set_budget(active_goal.goal_id, budget)

    if extra_context is None:
        extra_context = {}
    extra_context["goal_provider"] = goal_provider
    extra_context.setdefault("execution_mode", "pooled")

    try:
        from app.core.channel_bridge.config_loader import load_user_configs

        configs = await load_user_configs()
        if configs and configs.personal_settings_dict:
            locale = configs.personal_settings_dict.get("locale")
            if locale:
                extra_context["locale"] = locale
            suggest_wf = configs.personal_settings_dict.get("suggestWorkflowMode")
            if suggest_wf is not None:
                extra_context["suggest_workflow_mode"] = bool(suggest_wf)
    except Exception as e:
        logger.warning(f"Failed to load user locale for extra_context: {e}")

    is_long_running_task = request.action_mode in ("deep_research", "agentic_search", "consensus")
    collector = StreamContentCollector(sibling_group_id=request.sibling_group_id, chat_id=request.chat_id)

    consensus_config: dict[str, object] | None = None
    consensus_ref_cfgs: list[object] | None = None
    consensus_agg_cfg: object | None = None
    if request.action_mode == "consensus":
        ep = request.engine_params or {}
        raw_consensus = ep.get("consensus")
        if isinstance(raw_consensus, dict):
            consensus_config = raw_consensus  # type: ignore[assignment]
            try:
                from app.core.channel_bridge.config_loader import load_user_configs

                configs = await load_user_configs()
                pd = configs.providers_dict if configs else None
                ref_sels = raw_consensus.get("reference_model_selections", [])
                if isinstance(ref_sels, list):
                    resolved: list[object] = []
                    for sel in ref_sels:
                        if isinstance(sel, dict):
                            ms = ModelSelection(**sel)
                            mc = await _resolve_model_config(ms, pd)
                            if mc:
                                resolved.append(mc)
                    if resolved:
                        consensus_ref_cfgs = resolved
                agg_sel = raw_consensus.get("aggregator_model_selection")
                if isinstance(agg_sel, dict):
                    ms = ModelSelection(**agg_sel)
                    consensus_agg_cfg = await _resolve_model_config(ms, pd)
            except Exception:
                logger.warning("Failed to resolve consensus model selections")

    session = AgentStreamSession(
        request=request,
        http_request=http_request,
        params=params,
        cancel_token=cancel_token,
        steering_token=steering_token,
        routing_tier=routing_tier,
        context_warnings=context_warnings,
        archive_restore_results=archive_restore_results,
        research_model_cfg=research_model_cfg,
        registry=registry,
        collector=collector,
        monitor=CancellationMonitor(
            token=cancel_token,
            disconnect_checker=lambda: False,
            check_interval=0.5,
        ),
        is_long_running_task=is_long_running_task,
        goal_provider=goal_provider,
        extra_context=extra_context or {},
        consensus_config=consensus_config,
        consensus_ref_model_cfgs=consensus_ref_cfgs,
        consensus_agg_model_cfg=consensus_agg_cfg,
        entitlement_preflight_text=text_content if request.resume_value is None else None,
    )
    session.monitor = CancellationMonitor(
        token=cancel_token,
        disconnect_checker=build_disconnect_checker(session),
        check_interval=0.5,
    )

    return await launch_buffered_stream(session)
