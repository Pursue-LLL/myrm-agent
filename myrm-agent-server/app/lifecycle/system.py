"""Application lifecycle management."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.database.models.chat import InterruptedTurnMarker

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

                # Construct params from serialized state, dispatch to a background
                # task and consume the stream silently (Offline Guardian mode).
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
                        try:
                            from app.services.infra.system_notification import SystemNotificationService

                            await SystemNotificationService.create_notification(
                                title="Task Resume Failed",
                                message="A background task could not be resumed after a server restart. Please retry from the chat.",
                                type="error",
                                source="offline_guardian",
                                meta_data={
                                    "chat_id": task_record.chat_id,
                                    "action_url": f"/{task_record.chat_id}",
                                },
                            )
                        except Exception as notif_err:
                            logger.error("Failed to create resume failure notification: %s", notif_err)
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


_AUTO_CONTINUE_FRESHNESS_MINUTES = 15
_AUTO_CONTINUE_MAX_ATTEMPTS = 2


async def auto_continue_interrupted_turns() -> None:
    """Resume normal turns interrupted by a process crash.

    Scans ``interrupted_turn_markers`` for entries within the freshness window.
    For each qualifying marker, constructs a lightweight agent stream request
    and dispatches it in the background. The marker is cleaned up by the
    normal stream finalization path on success, or incremented and pruned
    on repeated failure (crash-loop breaker).
    """
    try:
        # Check user preference (default: enabled)
        try:
            from app.core.channel_bridge.config_loader import load_user_configs

            configs = await load_user_configs()
            if configs and configs.personal_settings_dict:
                enabled = configs.personal_settings_dict.get("autoContinueInterruptedTurns", True)
                if not enabled:
                    logger.info("[Startup] Auto-continue disabled by user preference")
                    return
        except Exception:
            pass  # Proceed with default (enabled) if config load fails

        from datetime import UTC, datetime, timedelta

        from sqlalchemy import delete, select

        from app.database.models.chat import InterruptedTurnMarker
        from app.platform_utils import get_session_factory

        session_factory = get_session_factory()
        cutoff = datetime.now(UTC) - timedelta(minutes=_AUTO_CONTINUE_FRESHNESS_MINUTES)

        async with session_factory() as db:
            await db.execute(
                delete(InterruptedTurnMarker).where(
                    (InterruptedTurnMarker.created_at < cutoff)
                    | (InterruptedTurnMarker.attempt_count >= _AUTO_CONTINUE_MAX_ATTEMPTS)
                )
            )
            await db.commit()

            result = await db.execute(select(InterruptedTurnMarker))
            markers = result.scalars().all()

        if not markers:
            return

        logger.info("[Startup] Found %d interrupted turn(s) eligible for auto-continue", len(markers))

        for marker in markers:
            asyncio.create_task(_dispatch_auto_continue(marker, session_factory))

    except Exception as e:
        logger.error("[Startup] Auto-continue interrupted turns failed: %s", e, exc_info=True)


async def _dispatch_auto_continue(
    marker: "InterruptedTurnMarker",
    session_factory: "async_sessionmaker[AsyncSession]",
) -> None:
    """Background worker: re-execute one interrupted turn and clean up."""
    from sqlalchemy import delete, update

    from app.database.models.chat import InterruptedTurnMarker

    try:
        # Increment attempt count first (crash-loop protection)
        async with session_factory() as db:
            await db.execute(
                update(InterruptedTurnMarker)
                .where(InterruptedTurnMarker.id == marker.id)
                .values(attempt_count=marker.attempt_count + 1)
            )
            await db.commit()

        if not marker.serialized_params:
            logger.warning("Auto-continue skipped for chat %s: missing params", marker.chat_id)
            return

        from myrm_agent_harness.utils.runtime.cancellation import CancellationToken

        from app.ai_agents import GeneralAgentParams
        from app.services.agent.streaming import ai_agent_service_stream

        params = GeneralAgentParams.model_validate(marker.serialized_params)
        params.message_id = f"auto_continue_{marker.id}"

        if not params.model_cfg:
            logger.warning("Auto-continue skipped for chat %s: missing model_cfg", marker.chat_id)
            return

        token = CancellationToken(request_id=params.message_id or marker.id)

        logger.info("[Auto-continue] Resuming interrupted turn for chat: %s", marker.chat_id)

        collected_parts: list[str] = []
        stream = ai_agent_service_stream(params=params, cancel_token=token)
        async for chunk in stream:
            if isinstance(chunk, dict) and chunk.get("type") == "message":
                data = chunk.get("data")
                if isinstance(data, str):
                    collected_parts.append(data)

        if collected_parts and marker.chat_id:
            from app.services.chat.chat_service import ChatService

            await ChatService.persist_assistant_message_safe(
                marker.chat_id,
                "".join(collected_parts),
                timezone=params.timezone,
            )

        logger.info("[Auto-continue] Completed for chat: %s", marker.chat_id)

        # Notify user
        from app.services.infra.system_notification import SystemNotificationService

        await SystemNotificationService.create_notification(
            title="Interrupted Turn Resumed",
            message="A conversation was automatically resumed after a restart.",
            type="success",
            source="auto_continue",
            meta_data={"chat_id": marker.chat_id, "action_url": f"/{marker.chat_id}"},
        )

    except Exception as e:
        logger.error("[Auto-continue] Failed for chat %s: %s", marker.chat_id, e, exc_info=True)
        try:
            from app.services.infra.system_notification import SystemNotificationService

            await SystemNotificationService.create_notification(
                title="Turn Resume Failed",
                message="Could not automatically resume an interrupted conversation. Please retry.",
                type="error",
                source="auto_continue",
                meta_data={"chat_id": marker.chat_id, "action_url": f"/{marker.chat_id}"},
            )
        except Exception as notif_err:
            logger.error("Failed to create auto-continue failure notification: %s", notif_err)
    finally:
        # Cleanup marker (stream_finalize may have already done this on success)
        try:
            async with session_factory() as db:
                await db.execute(
                    delete(InterruptedTurnMarker).where(InterruptedTurnMarker.id == marker.id)
                )
                await db.commit()
        except Exception as cleanup_err:
            logger.debug("Auto-continue marker cleanup: %s", cleanup_err)


async def pause_orphaned_active_goals() -> None:
    """Detect ACTIVE goals orphaned by a server restart and mark them PAUSED.

    On startup, any Goal still in ACTIVE state has no execution engine driving
    it (the async task died with the previous process). We transition them to
    PAUSED with a clear reason so the user can one-click Resume from the GUI.
    """
    try:
        from myrm_agent_harness.agent.goals.storage import GoalStorage
        from myrm_agent_harness.agent.goals.types import GoalStatus
        from myrm_agent_harness.toolkits.storage.factory import get_storage_provider

        storage = GoalStorage(get_storage_provider())
        active_sessions = await storage.list_active_sessions()

        if not active_sessions:
            return

        paused_count = 0
        for session_id in active_sessions:
            goal_id = await storage.get_active_goal_id(session_id)
            if not goal_id:
                continue

            goal = await storage.get_goal(goal_id)
            if not goal or goal.status != GoalStatus.ACTIVE:
                continue

            goal.status = GoalStatus.PAUSED
            goal.metadata["pause_reason"] = "Server restarted — resume when ready"
            await storage.save_goal(goal)
            paused_count += 1
            logger.info("Orphaned goal %s (session %s) paused after restart", goal_id, session_id)

        if paused_count:
            logger.info("Paused %d orphaned active goal(s) after server restart", paused_count)

            from app.services.infra.system_notification import SystemNotificationService

            await SystemNotificationService.create_notification(
                title="Goals Paused After Restart",
                message=f"{paused_count} goal(s) paused due to server restart. Resume from the chat.",
                type="warning",
                source="goal_recovery",
                meta_data={"paused_count": paused_count},
            )
    except Exception as e:
        logger.error("Failed to pause orphaned active goals: %s", e, exc_info=True)


async def start_idle_task_listeners() -> None:
    """Forward IdleTaskProgressEvent from Harness to ServerEventBus."""
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
