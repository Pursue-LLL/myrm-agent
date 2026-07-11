"""Agent Liveness SSOT — single aggregated endpoint for global agent state.

[INPUT]
@services.agent.gateway::AgentGateway (POS: Agent 执行网关，并发控制与生命周期)
@core.channel_bridge::get_channel_gateway (POS: 渠道网关单例，管理所有消息渠道)
@lifecycle.monitors::get_memory_pressure_monitor_instance (POS: 内存压力监控)

[OUTPUT]
GET /api/v1/health/liveness — aggregated agent liveness state

[POS]
Agent 全局存活状态 SSOT 端点。聚合 AgentGateway 活跃会话、渠道健康摘要、
内存压力等级为单一 JSON 响应，供前端 tray/Pet 三态指示器和运维监控使用。
"""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter

from app.services.agent.gateway import get_agent_gateway

logger = logging.getLogger(__name__)

router = APIRouter(tags=["liveness"])

_BOOT_MONOTONIC = time.monotonic()


@router.get("/liveness")
async def agent_liveness() -> dict[str, object]:
    """Global agent liveness state (SSOT).

    Returns a single JSON object that answers:
    - Is any agent currently running? (state: busy / idle / degraded)
    - Which sessions are active?
    - Are all channels healthy?
    - Is the system under memory pressure?

    Designed for:
    - Frontend tray / Pet three-state indicator (HV-02)
    - Cloud monitoring / curl health probes
    - Multi-pane workspace status bar
    """
    gateway = get_agent_gateway()

    active_sessions = gateway.get_active_sessions()
    active_count = gateway.active_count
    max_concurrent = gateway.config.max_per_user
    available_slots = gateway.get_available_slots()

    channels_summary = _build_channels_summary()
    memory = _build_memory_summary()

    has_degraded_channel = any(
        ch.get("status") in ("degraded", "error")
        for ch in channels_summary.values()
    ) if channels_summary else False

    if active_count > 0:
        state = "busy"
    elif has_degraded_channel or memory.get("level") in ("WARNING", "CRITICAL", "EMERGENCY"):
        state = "degraded"
    else:
        state = "idle"

    return {
        "state": state,
        "agents": {
            "activeCount": active_count,
            "maxConcurrent": max_concurrent,
            "availableSlots": available_slots,
            "sessions": active_sessions,
        },
        "channels": channels_summary,
        "memory": memory,
        "uptimeSeconds": round(time.monotonic() - _BOOT_MONOTONIC, 1),
    }


def _build_channels_summary() -> dict[str, dict[str, object]]:
    """Lightweight channel status aggregation from in-memory data."""
    try:
        from app.core.channel_bridge import get_channel_gateway

        gw = get_channel_gateway()
        statuses = gw.get_status()
        return {
            name: {"status": status.value}
            for name, status in statuses.items()
        }
    except Exception:
        return {}


def _build_memory_summary() -> dict[str, object]:
    """Current memory pressure level from the lifecycle monitor."""
    try:
        from app.lifecycle.monitors import get_memory_pressure_monitor_instance

        monitor = get_memory_pressure_monitor_instance()
        if monitor is not None:
            return {
                "level": monitor.current_level.name,
                "percent": round(monitor.current_memory_percent, 1),
            }
    except Exception:
        pass
    return {"level": "unknown", "percent": 0.0}
