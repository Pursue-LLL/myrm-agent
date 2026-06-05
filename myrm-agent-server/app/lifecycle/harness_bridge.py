"""
[INPUT] myrm_agent_harness.runtime.events::EventBus (POS: 框架层内部事件总线)
[INPUT] myrm_agent_harness.runtime.events.skill_events::SkillFailureEvent (POS: Framework-level skill failure event DTOs. They carry runtime evidence for business layers without importing product, GUI, approval, or tenant concepts.)
[INPUT] myrm_agent_harness.toolkits.mcp.lifecycle::mcp_lifecycle (POS: MCP lifecycle management for connection pool startup/shutdown)
[INPUT] app.services.event.app_event_bus::EventBus (POS: 业务层 SSE 应用级事件总线)
[INPUT] app.services.agent.gateway::AgentGateway (POS: 获取会话信息和智能体实例)
[INPUT] app.services.agent.evolution.skill_immune_service::handle_skill_failure_event (POS: 技能免疫业务服务。负责运行时技能失败的业务分类、幂等去重、修复提案生成与审批落地，不向 Harness 或 Control Plane 泄露产品语义。)
[OUTPUT] setup_harness_bridge: 启动事件桥接订阅
[OUTPUT] stop_harness_bridge: 停止 Harness 事件总线
[OUTPUT] close_harness_resources: 关闭 Harness 底层资源（事件总线 + MCP 持久连接池）
[POS] 框架事件桥接器。负责监听 Harness 层的微小状态事件，通过时间滑动窗口合并防抖后，聚合丰富数据转化为 Server 层的全量应用事件进行广播；并在应用关闭时统一释放 Harness 底层资源（事件总线 + MCP 持久连接池）。
"""

import asyncio
import logging

from myrm_agent_harness.runtime.events import get_event_bus as get_harness_bus
from myrm_agent_harness.runtime.events.skill_events import SkillFailureEvent
from myrm_agent_harness.runtime.events.system_events import (
    LocatorSelfHealedEvent,
    ResourceMetricsEvent,
    SubagentLifecycleEvent,
)

from app.services.agent.gateway import get_agent_gateway
from app.services.event.app_event_bus import AppEvent, AppEventType
from app.services.event.app_event_bus import get_event_bus as get_server_bus

logger = logging.getLogger(__name__)

# Debounce timer registry: session_id -> asyncio.TimerHandle
_pending_subagent_events: dict[str, asyncio.TimerHandle] = {}
_COALESCE_DELAY_SECONDS = 0.25


def _subagent_lifecycle_data_to_node(
    event: SubagentLifecycleEvent,
) -> dict[str, object] | None:
    if event.event_name != "policy_denied":
        return None
    data = event.data
    policy = data.policy
    policy_reason = policy.reason if policy else ""
    policy_details = policy.details if policy else ""
    return {
        "task_id": event.task_id,
        "agent_type": data.agent_type or (policy.agent_type if policy else "unknown"),
        "description": data.description,
        "status": "failed",
        "done": True,
        "cancelled": False,
        "role": data.role or (policy.requested_role if policy else ""),
        "control_scope": data.control_scope or (policy.effective_scope if policy else ""),
        "policy_reason": policy_reason,
        "policy_details": policy_details,
        "error": policy_details or policy_reason,
    }


async def _emit_subagent_tree(session_id: str) -> None:
    """Fetch the full tree and publish. Invoked after debounce period."""
    try:
        gateway = get_agent_gateway()
        info = gateway._session_info.get(session_id)

        children_data: list[dict[str, object]] = []
        if info and info.agent and info.agent() is not None:
            agent = info.agent()
            if hasattr(agent, "subagent_manager"):
                children_data.extend(agent.subagent_manager.list_children())

        # Also get checkpoints to build the full tree
        from myrm_agent_harness.agent.sub_agents.checkpoint.saver import (
            SubagentCheckpointStorage,
        )

        storage = SubagentCheckpointStorage()
        try:
            checkpoints = await storage.list_checkpoints(session_id=session_id)
            active_task_ids = {c.get("task_id") for c in children_data if isinstance(c, dict)}
            for c in checkpoints:
                if c.task_id not in active_task_ids:
                    status = "interrupted" if c.interruption_reason else "checkpoint"
                    node: dict[str, object] = {
                        "task_id": c.task_id,
                        "agent_type": c.agent_type,
                        "status": status,
                        "progress": c.progress,
                        "last_tool": c.last_tool,
                        "done": True,
                        "cancelled": True,
                    }
                    if c.interruption_reason:
                        node["interruption_reason"] = c.interruption_reason
                    if c.recovery_attempts > 0:
                        node["recovery_attempts"] = c.recovery_attempts
                    if c.task_description:
                        node["description"] = c.task_description
                    children_data.append(node)
        except Exception:
            logger.debug("Failed to list checkpoints in bridge")

        try:
            from myrm_agent_harness.agent.coordination.mailbox import (
                group_history_by_task,
                list_teammate_history,
            )

            from app.services.chat.chat_service import ChatService

            workspace_dir = await ChatService.ensure_default_workspace_dir(session_id)
            history = list_teammate_history(session_id, workspace_dir, limit=200)
            if history:
                grouped = group_history_by_task(history)
                for child in children_data:
                    if not isinstance(child, dict):
                        continue
                    task_id = child.get("task_id")
                    if isinstance(task_id, str) and task_id in grouped:
                        child["teammate_messages"] = grouped[task_id]
        except Exception:
            logger.debug("Failed to hydrate teammate messages in bridge", exc_info=True)

        get_server_bus().publish(
            AppEvent(
                event_type=AppEventType.SUBAGENTS_UPDATED,
                data={"chat_id": session_id, "tree": children_data},
            )
        )
    except Exception as e:
        logger.error("Error emitting coalesced subagent tree: %s", e)
    finally:
        _pending_subagent_events.pop(session_id, None)


async def _handle_subagent_event(event: SubagentLifecycleEvent) -> None:
    session_id = event.session_id
    if not session_id:
        return

    policy_node = _subagent_lifecycle_data_to_node(event)
    if policy_node is not None:
        get_server_bus().publish(
            AppEvent(
                event_type=AppEventType.SUBAGENTS_UPDATED,
                data={"chat_id": session_id, "tree": [policy_node]},
            )
        )
        return

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return

    # Fixed-Window Throttle: If a timer is already running, do nothing.
    # The running timer will eventually fire, collecting the latest state.
    if session_id in _pending_subagent_events:
        return

    # Schedule the tree building and emission after a short delay
    _pending_subagent_events[session_id] = loop.call_later(
        _COALESCE_DELAY_SECONDS,
        lambda: asyncio.create_task(_emit_subagent_tree(session_id)),
    )


async def _handle_resource_event(event: ResourceMetricsEvent) -> None:
    try:
        get_server_bus().publish(
            AppEvent(
                event_type=AppEventType.MEMORY_HISTORY_UPDATED,
                data={"history": event.history},
            )
        )
    except Exception as e:
        logger.error("Failed to publish memory history: %s", e)


async def _handle_skill_failure_event(event: SkillFailureEvent) -> None:
    try:
        from app.services.agent.evolution.skill_immune_service import (
            handle_skill_failure_event,
        )

        await handle_skill_failure_event(event)
    except Exception as exc:
        logger.error("Failed to handle skill failure event: %s", exc, exc_info=True)


async def _handle_locator_healed_event(event: LocatorSelfHealedEvent) -> None:
    try:
        get_server_bus().publish(
            AppEvent(
                event_type=AppEventType.LOCATOR_HEALED,
                data=event.to_dict(),
            )
        )
    except Exception as e:
        logger.error("Failed to publish locator healed event: %s", e)


def setup_harness_bridge() -> None:
    """Setup subscriptions from Harness EventBus to Server EventBus."""
    bus = get_harness_bus()
    bus.start()
    bus.subscribe(SubagentLifecycleEvent, _handle_subagent_event)
    bus.subscribe(ResourceMetricsEvent, _handle_resource_event)
    bus.subscribe(SkillFailureEvent, _handle_skill_failure_event)
    bus.subscribe(LocatorSelfHealedEvent, _handle_locator_healed_event)

    from myrm_agent_harness.agent.sub_agents.checkpoint.orphan_recovery import (
        OrphanRecoveryManager,
    )

    OrphanRecoveryManager.get_instance().schedule_scan()

    logger.info("Harness event bridge setup complete.")


async def stop_harness_bridge() -> None:
    """Stop the Harness EventBus."""
    bus = get_harness_bus()
    await bus.stop()
    logger.info("Harness event bridge stopped.")


async def close_harness_resources() -> None:
    """Close all underlying Harness resources like database connections."""
    try:
        await stop_harness_bridge()
    except Exception as e:
        logger.error("Error during harness bridge teardown: %s", e)

    # Persistent MCP sessions keep subprocesses/connections warm for their whole
    # lifetime, so they must be drained on shutdown (otherwise reloads leak them).
    try:
        from myrm_agent_harness.toolkits.mcp.lifecycle import mcp_lifecycle

        await mcp_lifecycle.shutdown()
    except Exception as e:
        logger.error("Error during MCP connection pool teardown: %s", e)
