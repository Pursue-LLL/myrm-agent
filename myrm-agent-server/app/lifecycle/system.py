"""Application lifecycle management."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


async def start_channel_gateway() -> None:
    """启动 Channel Gateway（支持多种聊天平台集成）"""
    from app.core.channel_bridge.setup import start_channel_gateway as _start_gateway

    await _start_gateway()


async def init_risk_rules() -> None:
    """Seed built-in risk rules and initialize the detection engine."""
    try:
        from app.platform_utils import get_session_factory
        from app.services.risk.detection import get_detection_service
        from app.services.risk.rule_service import RiskRuleService

        session_factory = get_session_factory()
        async with session_factory() as db:
            inserted = await RiskRuleService().seed_builtin_rules(db)
            await db.commit()
            if inserted > 0:
                logger.info("Seeded %d built-in risk rules on startup", inserted)
            await get_detection_service().reload(db)
        logger.info("Risk detection engine initialized")
    except Exception as e:
        logger.error("Risk rule initialization failed: %s", e)


async def init_allowlist_store() -> None:
    """初始化白名单持久化存储（HITL 审批系统）。

    使用数据库持久化用户的"始终允许"规则，重启后自动恢复。
    """
    try:
        from myrm_agent_harness.agent.security.approval_flow import set_allowlist_store

        from app.database.allowlist_store import DBAllowlistStore
        from app.platform_utils import session_factory

        store = DBAllowlistStore(session_factory)
        set_allowlist_store(store)
        logger.info("Allowlist store: Database (persistent)")
    except Exception as e:
        logger.error("Allowlist store initialization failed: %s", e)


async def resume_durable_offline_tasks() -> None:
    """Resume interrupted background tasks on server startup.

    Reads from the offline_durable_tasks table and uses the LangGraph
    checkpointer to restart the state machines for tasks that were
    abandoned due to a server crash or restart.
    """
    try:
        from sqlalchemy import select

        from app.database.models.chat import OfflineDurableTask
        from app.platform_utils import get_checkpointer, get_session_factory

        checkpointer = get_checkpointer()
        if not checkpointer:
            logger.warning("Checkpointer not available, skipping durable task resume")
            return

        session_factory = get_session_factory()
        async with session_factory() as db:
            result = await db.execute(select(OfflineDurableTask))
            tasks = result.scalars().all()

            if not tasks:
                return

            logger.info(f"🔄 Found {len(tasks)} interrupted offline tasks. Attempting resume...")

            for task in tasks:
                logger.info(f"▶️ Resuming durable task for chat: {task.chat_id} (action: {task.action_mode})")

                # Mock or dispatch to a background worker
                # In actual implementation, we would construct an AgentRequest
                # and call ai_agent_service_stream or deep_research_stream with the thread_id.
                # Since streaming expects a response stream, we run it in a background task
                # and consume the stream silently (acting as the Offline Guardian).
                from myrm_agent_harness.utils.runtime.cancellation import CancellationToken

                from app.ai_agents import GeneralAgentParams

                async def _background_resume_worker(task_record: OfflineDurableTask) -> None:
                    try:
                        # Construct minimal params to resume from checkpoint
                        from typing import cast

                        from app.services.agent.params import _extract_text_from_query
                        from app.services.agent.params.models import MultimodalQuery

                        if not task_record.serialized_params:
                            logger.warning(
                                "Skipping offline resume for task %s: missing serialized_params",
                                task_record.id,
                            )
                            return

                        params = GeneralAgentParams.model_validate(task_record.serialized_params)
                        params.message_id = task_record.id  # Use task ID as trace

                        if not params.model_cfg:
                            logger.warning(
                                "Skipping offline resume for task %s: missing model_cfg in serialized params",
                                task_record.id,
                            )
                            return

                        token = CancellationToken(request_id=task_record.id)

                        if task_record.action_mode in ("deep_research", "agentic_search"):
                            from myrm_agent_harness.toolkits.llms import llm_manager

                            from app.services.agent.streaming import ai_deep_research_service_stream

                            llm = await llm_manager.get_llm_from_config(params.model_cfg)

                            raw_q = params.query
                            if isinstance(raw_q, str) or isinstance(raw_q, list):
                                text_query = _extract_text_from_query(cast(MultimodalQuery, raw_q))
                            else:
                                text_query = ""

                            stream = ai_deep_research_service_stream(
                                llm=llm,
                                query=text_query,
                                message_id=params.message_id or "",
                                chat_history=[],
                                parent_tools=[],
                                cancel_token=token,
                                context={"session_id": params.chat_id or ""},
                            )
                        else:
                            from app.services.agent.streaming import ai_agent_service_stream

                            stream = ai_agent_service_stream(params=params, cancel_token=token)

                        # Consume stream silently
                        async for _chunk in stream:
                            pass

                        logger.info(f"✅ Resumed task completed for chat: {task_record.chat_id}")

                        # Notify user
                        from app.services.infra.system_notification import SystemNotificationService

                        await SystemNotificationService.create_notification(
                            title="Task Completed (Offline Guardian Resume)",
                            message="Your background task has successfully completed after a server restart.",
                            type="success",
                            source="offline_guardian",
                            meta_data={
                                "chat_id": task_record.chat_id,
                                "action_url": f"/{task_record.chat_id}",
                            },
                        )

                    except Exception as e:
                        logger.error(f"❌ Failed to resume task {task_record.chat_id}: {e}", exc_info=True)
                    finally:
                        # Cleanup the registration
                        try:
                            from sqlalchemy import delete

                            async with session_factory() as cleanup_db:
                                await cleanup_db.execute(
                                    delete(OfflineDurableTask).where(OfflineDurableTask.id == task_record.id)
                                )
                                await cleanup_db.commit()
                        except Exception as e:
                            logger.error(f"Failed to cleanup task record {task_record.chat_id}: {e}")

                asyncio.create_task(_background_resume_worker(task))

    except Exception as e:
        logger.error(f"Failed to initialize durable offline tasks: {e}", exc_info=True)


async def start_idle_task_listeners() -> None:
    """Forward IdleTaskProgressEvent from Harness to Server EventBus."""
    try:
        from myrm_agent_harness.runtime.events.bus import get_event_bus as get_harness_bus
        from myrm_agent_harness.runtime.events.idle_events import IdleTaskProgressEvent

        from app.services.event.app_event_bus import AppEvent, AppEventType
        from app.services.event.app_event_bus import get_event_bus as get_server_bus

        harness_bus = get_harness_bus()
        server_bus = get_server_bus()

        async def _forward_idle_event(event: IdleTaskProgressEvent) -> None:
            server_bus.publish(
                AppEvent(
                    event_type=AppEventType.IDLE_STATUS,
                    data={
                        "session_id": event.session_id,
                        "status": event.status,
                        "task_name": event.task_name,
                        "progress_pct": event.progress_pct,
                        "message": event.message,
                        "data": event.data,
                    },
                )
            )

            # If task completed successfully, save to offline inbox
            if event.status == "completed":
                # Route CAPTURED skill proposals through unified growth lifecycle
                if (
                    event.task_name == "session_evidence_extraction"
                    and event.data
                    and "proposal" in event.data
                    and event.data["proposal"]
                ):
                    proposal = event.data["proposal"]
                    recommended_form = proposal.get("recommended_form", "skill")
                    if recommended_form == "skip":
                        logger.debug(
                            "CAPTURED proposal '%s' skipped (form=skip)",
                            proposal.get("skill_id"),
                        )
                    else:
                        from app.services.skills.growth_lifecycle import process_skill_review_result

                        _form_type_map = {"skill": "skill_draft", "cron_job": "cron_suggestion"}
                        growth_type = _form_type_map.get(recommended_form, "skill_draft")

                        try:
                            payload: dict = {
                                "type": growth_type,
                                "has_value": True,
                                "skill_name": proposal.get("skill_id"),
                                "skill_description": proposal.get("reasoning"),
                                "content": proposal.get("proposed_content"),
                                "score": proposal.get("score"),
                                "agent_id": proposal.get("agent_id", "default"),
                                "chat_id": proposal.get("chat_id"),
                            }
                            if proposal.get("form_metadata"):
                                payload["form_metadata"] = proposal["form_metadata"]
                            await process_skill_review_result(payload)
                            logger.info(
                                "CAPTURED skill proposal '%s' routed through growth lifecycle (form=%s)",
                                proposal.get("skill_id"),
                                recommended_form,
                            )
                        except Exception as e:
                            logger.error("Failed to process CAPTURED skill proposal: %s", e, exc_info=True)

                from app.database.connection import get_session
                from app.database.models.notification import SystemNotification

                try:
                    async with get_session() as session:
                        notification = SystemNotification(
                            title=f"后台任务已完成: {event.task_name or '未知任务'}",
                            message=event.message or "任务成功执行完毕",
                            type="success",
                            source="idle_daemon",
                            meta_data=event.data or {},
                        )
                        session.add(notification)
                        await session.commit()

                        server_bus.publish(
                            AppEvent(
                                event_type=AppEventType.SYSTEM_NOTIFICATION,
                                data={
                                    "title": notification.title,
                                    "message": notification.message,
                                    "type": notification.type,
                                    "meta_data": notification.meta_data,
                                },
                            )
                        )
                except Exception as ex:
                    logger.error(f"Failed to save system notification for idle task: {ex}")

        harness_bus.subscribe(IdleTaskProgressEvent, _forward_idle_event)
        logger.info("Idle task listeners successfully started")
    except Exception as e:
        logger.error(f"Failed to start idle task listeners: {e}", exc_info=True)
