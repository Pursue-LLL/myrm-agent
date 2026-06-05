"""SSE chunk generation for agent stream sessions.

[INPUT]
- app.services.agent.stream_session.stream_session_types (POS: 会话上下文数据类)
- app.services.agent.stream_loop (POS: Agent SSE 主流循环)
- app.services.agent.stream_finalize (POS: 流错误处理与会话 teardown)

[OUTPUT]
- generate_cancellable_stream: 可取消的 SSE chunk 异步生成器

[POS]
Agent 流式 SSE chunk 编排：凭据注入、预检事件、Vision fallback，委托 loop/finalize。
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
from app.services.agent.stream_session.stream_loop import ApprovalTimeoutHolder, iter_agent_stream_chunks
from app.services.agent.stream_session.stream_session_types import AgentStreamSession
from app.services.agent.streaming_support.sse_failover_emitter import (
    SSEFailoverEmitter,
    merge_stream_with_emitter,
)

logger = logging.getLogger(__name__)


async def generate_cancellable_stream(session: AgentStreamSession) -> AsyncGenerator[str, None]:
    from myrm_agent_harness.agent.security import (
        EphemeralUserCredential,
        user_credentials_ctx,
    )

    from app.core.channel_bridge.config_loader import load_user_configs

    credentials_list: list[EphemeralUserCredential] = []
    try:
        configs = await load_user_configs()
        if configs and configs.oauth_credentials_dict:
            from app.services.agent.oauth_refresher import refresh_oauth_token

            for issuer, cred_val in configs.oauth_credentials_dict.items():
                if isinstance(cred_val, dict) and "token" in cred_val:
                    credentials_list.append(
                        EphemeralUserCredential(
                            issuer=issuer,
                            token=str(cred_val["token"]),
                            scope=str(cred_val.get("scope", "")),
                            user_id=str(cred_val.get("user_id", "")),
                            expires_at=cred_val.get("expires_at"),
                            refresh_callback=lambda i=issuer: refresh_oauth_token(i),
                        )
                    )
    except Exception as e:
        logger.warning("Failed to resolve user configs/credentials in web stream: %s", e)

    token_ctx = user_credentials_ctx.set(tuple(credentials_list))
    approval = ApprovalTimeoutHolder()

    if session.routing_tier:
        routing_data: dict[str, object] = {"tier": session.routing_tier}
        routing_event_data: dict[str, object] = {
            "type": "routing_decision",
            "messageId": session.params.message_id or "",
            "data": cast(dict[str, object], routing_data),
        }
        session.collector.feed_event(routing_event_data)
        yield SSEEnvelope.from_any(routing_event_data).to_sse_chunk()

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
            if has_images:
                yield SSEEnvelope.from_any(
                    {
                        "type": "status",
                        "messageId": session.params.message_id,
                        "step_key": "analyzing_image",
                    }
                ).to_sse_chunk()
            if has_videos:
                yield SSEEnvelope.from_any(
                    {
                        "type": "status",
                        "messageId": session.params.message_id,
                        "step_key": "analyzing_video",
                    }
                ).to_sse_chunk()

            processed_query = await _process_human_content(
                session.params.query,
                meta=meta,
                model_cfg=session.params.model_cfg,
                vision_fallback_model_cfg=session.params.vision_fallback_model_cfg,
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
                    iter_agent_stream_chunks(session, approval),
                    failover_emitter,
                ):
                    yield chunk
            except BaseException as exc:
                async for chunk in yield_stream_exception_chunks(session, exc):
                    yield chunk
    finally:
        failover_emitter.close()
        await finalize_agent_stream_session(session, token_ctx, approval)
