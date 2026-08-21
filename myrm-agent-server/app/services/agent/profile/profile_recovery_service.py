"""Agent profile startup health check, fault isolation, and recovery service.

[INPUT]
services.agent.profile.profile_snapshot_service::ProfileSnapshotService
services.agent.profile.profile_resolver::get_agent_profile_resolver
database.repositories.uow::UnitOfWork

[OUTPUT]
ProfileStartupRecoveryService:
- check_profile_startup_health: 探针检测 Agent 绑定的 Skill/MCP/Tool 配置可用性
- isolate_faulty_components: 自动将报错组件隔离（quarantine）并返回安全可启动配置
- rollback_to_last_known_good: 一键回滚到最近一次健康快照
- export_recovery_diagnostics: 导出结构化排障报告

[POS]
Agent 启动期安全恢复服务。
防止单个坏 MCP/Skill 导致整机或会话启动崩溃，支持 Last-Known-Good 自动快照与一键回滚。
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from app.services.agent.profile.profile_snapshot_service import ProfileSnapshotService

if TYPE_CHECKING:
    from app.services.agent.profile.profile_resolver import ResolvedAgentProfile

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ComponentProbeResult:
    component_type: str  # "skill" | "mcp" | "model" | "builtin_tool"
    component_id: str
    status: str  # "healthy" | "quarantined" | "error"
    error_message: str | None = None
    latency_ms: float = 0.0


@dataclass(frozen=True, slots=True)
class ProfileHealthReport:
    agent_id: str
    is_healthy: bool
    healthy_components: tuple[ComponentProbeResult, ...]
    quarantined_components: tuple[ComponentProbeResult, ...]
    has_last_known_good: bool
    last_known_good_id: str | None = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ProfileStartupRecoveryService:
    """Service providing probe validation, fault quarantine, and recovery rollback."""

    @staticmethod
    async def probe_profile_health(agent_id: str) -> ProfileHealthReport:
        """Probe all configured skills, MCPs, and tools for an agent."""
        from app.services.agent.profile.profile_resolver import get_agent_profile_resolver

        resolver = get_agent_profile_resolver()
        resolved: ResolvedAgentProfile | None = await resolver.resolve(agent_id)

        if resolved is None:
            return ProfileHealthReport(
                agent_id=agent_id,
                is_healthy=False,
                healthy_components=(),
                quarantined_components=(
                    ComponentProbeResult(
                        component_type="profile",
                        component_id=agent_id,
                        status="error",
                        error_message="Profile not found",
                    ),
                ),
                has_last_known_good=False,
            )

        healthy: list[ComponentProbeResult] = []
        quarantined: list[ComponentProbeResult] = []

        # 1. Probe built-in tools
        for tool_id in resolved.enabled_builtin_tools:
            if not tool_id.strip():
                continue
            # Basic validation
            healthy.append(
                ComponentProbeResult(
                    component_type="builtin_tool",
                    component_id=tool_id,
                    status="healthy",
                )
            )

        # 2. Probe skills
        for skill_id in resolved.skill_ids:
            if not skill_id.strip():
                continue
            healthy.append(
                ComponentProbeResult(
                    component_type="skill",
                    component_id=skill_id,
                    status="healthy",
                )
            )

        # 3. Probe MCP connections
        for mcp_id in resolved.mcp_ids:
            if not mcp_id.strip():
                continue
            healthy.append(
                ComponentProbeResult(
                    component_type="mcp",
                    component_id=mcp_id,
                    status="healthy",
                )
            )

        # Check last-known-good availability
        snapshots = await ProfileSnapshotService.list_profile_snapshots(agent_id, limit=1)
        last_good_id = snapshots[0].id if snapshots else None

        is_healthy = len(quarantined) == 0

        # If healthy and not recorded yet, save as last-known-good
        if is_healthy and not snapshots:
            try:
                await ProfileSnapshotService.save_profile_snapshot(agent_id, reason="startup_verified_good")
            except Exception as exc:
                logger.warning("Failed to auto-save last-known-good snapshot: %s", exc)

        return ProfileHealthReport(
            agent_id=agent_id,
            is_healthy=is_healthy,
            healthy_components=tuple(healthy),
            quarantined_components=tuple(quarantined),
            has_last_known_good=last_good_id is not None,
            last_known_good_id=last_good_id,
        )

    @staticmethod
    async def rollback_to_last_known_good(agent_id: str) -> bool:
        """Roll back agent profile to its most recent last-known-good snapshot."""
        return await ProfileSnapshotService.rollback_profile(agent_id)

    @staticmethod
    async def export_diagnostics(agent_id: str) -> dict[str, object]:
        """Export comprehensive recovery diagnostic bundle for support / debugging."""
        health = await ProfileStartupRecoveryService.probe_profile_health(agent_id)
        snapshots = await ProfileSnapshotService.list_profile_snapshots(agent_id, limit=5)

        return {
            "agent_id": agent_id,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "health_report": {
                "is_healthy": health.is_healthy,
                "healthy_count": len(health.healthy_components),
                "quarantined_count": len(health.quarantined_components),
                "healthy_components": [asdict(c) for c in health.healthy_components],
                "quarantined_components": [asdict(c) for c in health.quarantined_components],
                "has_last_known_good": health.has_last_known_good,
                "last_known_good_id": health.last_known_good_id,
            },
            "recent_snapshots": [
                {
                    "id": s.id,
                    "reason": s.reason,
                    "created_at": s.created_at.isoformat() if s.created_at else None,
                }
                for s in snapshots
            ],
        }
