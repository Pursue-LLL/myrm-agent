"""SSE chunk generation for agent stream sessions.

[INPUT]
- app.services.agent.stream_session.stream_session_types (POS: 会话上下文数据类)
- app.services.agent.stream_loop (POS: Agent SSE 主流循环)
- app.services.agent.stream_finalize (POS: 流错误处理与会话 teardown)

[OUTPUT]
- generate_cancellable_stream: 可取消的 SSE chunk 异步生成器

[POS]
Agent 流式 SSE chunk 编排：凭据注入、config / migration readiness / entitlement 三轨 gap 预检、Vision fallback，委托 loop/finalize。
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from typing import cast

from myrm_agent_harness.toolkits.llms.fallback import with_failover_emitter

from app.schemas.streaming import SSEEnvelope
from app.services.agent.stream_session.stream_finalize import (
    finalize_agent_stream_session,
    yield_stream_exception_chunks,
)
from app.services.agent.stream_session.stream_loop import (
    ApprovalTimeoutHolder,
    ClarificationTimeoutHolder,
    iter_agent_stream_chunks,
)
from app.services.agent.stream_session.stream_session_types import AgentStreamSession
from app.services.agent.streaming_support.sse_failover_emitter import (
    SSEFailoverEmitter,
    merge_stream_with_emitter,
)

logger = logging.getLogger(__name__)


async def generate_cancellable_stream(
    session: AgentStreamSession,
) -> AsyncGenerator[str, None]:
    from myrm_agent_harness.agent.security import (
        EphemeralUserCredential,
        user_credentials_ctx,
    )

    from app.core.channel_bridge.config_loader import load_user_configs
    from app.services.agent.session_credential_assembler import (
        assemble_session_credentials,
    )

    credentials_list: tuple[EphemeralUserCredential, ...] = ()
    try:
        configs = await load_user_configs()
        credentials_list = await assemble_session_credentials(
            oauth_credentials_dict=configs.oauth_credentials_dict if configs else None,
            providers_dict=configs.providers_dict if configs else None,
        )
    except Exception as e:
        logger.warning("Failed to resolve user configs/credentials in web stream: %s", e)

    token_ctx = user_credentials_ctx.set(credentials_list)
    approval = ApprovalTimeoutHolder()
    clarification = ClarificationTimeoutHolder()

    from myrm_agent_harness.core.config import ModelTier, infer_model_tier

    _custom_def = getattr(session.params.model_cfg, "custom_model_def", None)
    _max_ctx = getattr(session.params.model_cfg, "max_context_tokens", None)
    _model_tier = infer_model_tier(session.params.model_cfg.model, _custom_def, _max_ctx)

    if session.routing_tier or session.routing_specialty:
        routing_data: dict[str, object] = {}
        if session.routing_tier:
            routing_data["tier"] = session.routing_tier
        if session.routing_specialty:
            routing_data["specialty"] = session.routing_specialty
        if session.routing_reason:
            routing_data["reason"] = session.routing_reason
        if _model_tier != ModelTier.STRONG:
            routing_data["model_tier"] = _model_tier.value

        routing_event_data: dict[str, object] = {
            "type": "routing_decision",
            "messageId": session.params.message_id or "",
            "data": cast(dict[str, object], routing_data),
        }
        session.collector.feed_event(routing_event_data)
        yield SSEEnvelope.from_any(routing_event_data).to_sse_chunk()
    elif _model_tier != ModelTier.STRONG:
        model_tier_event: dict[str, object] = {
            "type": "routing_decision",
            "messageId": session.params.message_id or "",
            "data": cast(dict[str, object], {"model_tier": _model_tier.value}),
        }
        session.collector.feed_event(model_tier_event)
        yield SSEEnvelope.from_any(model_tier_event).to_sse_chunk()

    if session.context_warnings:
        for warning_msg in session.context_warnings:
            warning_event_data: dict[str, object] = {
                "type": "context_reference_warning",
                "messageId": session.params.message_id or "",
                "data": {"message": warning_msg},
            }
            yield SSEEnvelope.from_any(warning_event_data).to_sse_chunk()

    if session.archive_restore_results:
        for result in session.archive_restore_results:
            restore_event_data: dict[str, object] = {
                "type": "status",
                "messageId": session.params.message_id or "",
                "step_key": "archive_restore_result",
                "status": "success",
                "data": {"archive_restore_result": result},
            }
            session.collector.feed_event(restore_event_data)
            yield SSEEnvelope.from_any(restore_event_data).to_sse_chunk()

    if session.request.resume_value is None:
        from app.services.agent.stream_session.entitlement_gap_preflight import (
            build_web_search_config_gap_sse_event,
        )
        from app.services.agent.stream_session.migration_readiness_preflight import (
            resolve_and_build_migration_readiness_gap_sse_event,
        )

        search_gap_event = build_web_search_config_gap_sse_event(
            message_id=session.params.message_id or "",
            web_search_profile_enabled=bool(getattr(session.params, "web_search_profile_enabled", False)),
            enable_web_search=bool(session.params.enable_web_search),
            search_is_user_configured=bool(getattr(session.params, "search_is_user_configured", False)),
            chat_id=session.request.chat_id,
            locale=getattr(session.params, "locale", None),
        )
        if search_gap_event is not None:
            session.collector.feed_event(search_gap_event)
            yield SSEEnvelope.from_any(search_gap_event).to_sse_chunk()

        migration_gap_event, migration_live_status = await resolve_and_build_migration_readiness_gap_sse_event(
            message_id=session.params.message_id or "",
            migration_readiness_anchor=session.request.migration_readiness_anchor,
            chat_id=session.request.chat_id,
            locale=getattr(session.params, "locale", None),
        )
        if migration_live_status is not None:
            session.migration_live_readiness_status = migration_live_status
        if migration_gap_event is not None:
            session.collector.feed_event(migration_gap_event)
            yield SSEEnvelope.from_any(migration_gap_event).to_sse_chunk()

    if session.entitlement_preflight_text:
        from app.ai_agents.general_agent.active_tool_groups import (
            derive_active_tool_groups_from_params,
        )
        from app.services.agent.stream_session.entitlement_gap_preflight import (
            build_surface_unavailable_gap_sse_event,
        )

        surface_gap_event = build_surface_unavailable_gap_sse_event(
            message_id=session.params.message_id or "",
            user_text=session.entitlement_preflight_text,
            active_tool_groups=derive_active_tool_groups_from_params(session.params),
            chat_id=session.request.chat_id,
            channel_name=getattr(session.params, "channel_name", "web_chat"),
            client_surface=getattr(session.params, "client_surface", None),
            locale=getattr(session.params, "locale", None),
        )
        if surface_gap_event is not None:
            session.collector.feed_event(surface_gap_event)
            yield SSEEnvelope.from_any(surface_gap_event).to_sse_chunk()

    if session.request.resume_value is None and isinstance(session.extra_context, dict):
        still_warming = bool(session.extra_context.get("turn_prewarm_still_warming"))
        brief_status = session.extra_context.get("memory_brief_status")
        if still_warming:
            agent_warm_event: dict[str, object] = {
                "type": "status",
                "messageId": session.params.message_id,
                "step_key": "turn_prewarm_agent",
                "status": "waiting",
            }
            session.collector.feed_event(agent_warm_event)
            yield SSEEnvelope.from_any(agent_warm_event).to_sse_chunk()

        if isinstance(brief_status, dict) and brief_status.get("reason") == "brief_pending":
            brief_warm_event: dict[str, object] = {
                "type": "status",
                "messageId": session.params.message_id,
                "step_key": "turn_prewarm_memory",
                "status": "waiting",
            }
            session.collector.feed_event(brief_warm_event)
            yield SSEEnvelope.from_any(brief_warm_event).to_sse_chunk()

    await session.monitor.start()

    if isinstance(session.params.query, list) and session.request.resume_value is None:
        from app.core.utils.chat_utils import _process_human_content

        meta = {
            "message_id": session.params.message_id,
            "chat_id": session.params.chat_id,
            "extra_data": {"original_query": session.request.query},
        }
        try:
            has_images = any(
                isinstance(item, dict) and item.get("type") in ("image_url", "image") for item in session.params.query
            )
            has_videos = any(
                isinstance(item, dict) and item.get("type") == "video_url" for item in session.params.query
            ) and not getattr(session.params.model_cfg, "supports_video", False)
            from app.core.channel_bridge.config_parsers import (
                extract_video_fallback_model_configs,
            )

            video_fallback_cfgs = session.params.video_fallback_model_cfgs
            if not video_fallback_cfgs and configs and configs.providers_dict:
                video_fallback_cfgs = extract_video_fallback_model_configs(configs.providers_dict)

            if has_images:
                image_status: dict[str, object] = {
                    "type": "status",
                    "messageId": session.params.message_id,
                    "step_key": "analyzing_image",
                }
                if session.params.vision_fallback_model_cfg or session.params.vision_fallback_model_cfgs:
                    image_status["data"] = {"vision_backend": "vlm"}
                yield SSEEnvelope.from_any(image_status).to_sse_chunk()
            if has_videos:
                video_status: dict[str, object] = {
                    "type": "status",
                    "messageId": session.params.message_id,
                    "step_key": "analyzing_video",
                }
                if video_fallback_cfgs:
                    use_native = any(getattr(cfg, "supports_video", False) for cfg in video_fallback_cfgs)
                    video_status["data"] = {"vision_backend": "native_video" if use_native else "frame"}
                yield SSEEnvelope.from_any(video_status).to_sse_chunk()

            processed_query = await _process_human_content(
                session.params.query,
                meta=meta,
                model_cfg=session.params.model_cfg,
                vision_fallback_model_cfg=session.params.vision_fallback_model_cfg,
                vision_fallback_model_cfgs=session.params.vision_fallback_model_cfgs,
                video_fallback_model_cfgs=video_fallback_cfgs or None,
            )
            session.params.query = processed_query

            if has_images:
                yield SSEEnvelope.from_any(
                    {
                        "type": "status",
                        "messageId": session.params.message_id,
                        "step_key": "analyzing_image_clear",
                    }
                ).to_sse_chunk()
            if has_videos:
                yield SSEEnvelope.from_any(
                    {
                        "type": "status",
                        "messageId": session.params.message_id,
                        "step_key": "analyzing_video_clear",
                    }
                ).to_sse_chunk()
        except Exception as e:
            logger.warning("Failed to process human content for current query: %s", e)

    failover_emitter = SSEFailoverEmitter(
        message_id=session.params.message_id,
        collector=session.collector,
    )

    try:
        async with with_failover_emitter(failover_emitter):
            try:
                async for chunk in merge_stream_with_emitter(
                    iter_agent_stream_chunks(session, approval, clarification),
                    failover_emitter,
                ):
                    yield chunk
            except BaseException as exc:
                async for chunk in yield_stream_exception_chunks(session, exc):
                    yield chunk
    finally:
        failover_emitter.close()
        await finalize_agent_stream_session(session, token_ctx, approval, clarification)
