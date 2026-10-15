"""Application lifecycle management.

[INPUT]
- app.core.channel_bridge.setup::start_channel_gateway (POS: 渠道网关启动器)
- app.database.allowlist_store::DBAllowlistStore (POS: HITL 白名单持久化存储)
- myrm_agent_harness.agent.goals.storage::GoalStorage (POS: 目标存储)
- app.services.event.app_event_bus::AppEventBus (POS: 业务层 SSE 应用级事件总线)

[OUTPUT]
- start_channel_gateway: 启动渠道网关（多聊天平台集成）
- init_allowlist_store: 初始化 HITL 白名单持久化存储
- pause_orphaned_active_goals: 重启后暂停孤儿活跃目标
- start_idle_task_listeners: 转发 IdleTask 进度事件到 ServerEventBus

[POS]
启动编排层。聚合渠道网关、HITL 白名单、孤儿 Goal 暂停、
空闲任务监听等系统组件在启动时的初始化与编排。
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def start_channel_gateway() -> None:
    """启动 Channel Gateway（支持多种聊天平台集成）"""
    from app.core.channel_bridge.setup import start_channel_gateway as _start_gateway

    await _start_gateway()


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


async def init_workspace_trust_store() -> None:
    """Initialize workspace trust registry and inject harness lookup."""
    try:
        from app.services.security.workspace_trust_store import init_workspace_trust_store as _init

        await _init()
    except Exception as e:
        logger.error("Workspace trust store initialization failed: %s", e)


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
                        "data": event.data,
                    },
                )
            )

        harness_bus.subscribe(IdleTaskProgressEvent, _forward_idle_event)
        logger.info("Idle task listeners successfully started")
    except Exception as e:
        logger.error(f"Failed to start idle task listeners: {e}", exc_info=True)
