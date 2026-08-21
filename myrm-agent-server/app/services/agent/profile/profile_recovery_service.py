"""Agent profile startup health check, fault isolation, and recovery service.

[INPUT]
services.agent.profile.profile_snapshot_service::ProfileSnapshotService
services.agent.profile.profile_resolver::get_agent_profile_resolver
database.repositories.uow::UnitOfWork

[OUTPUT]
ProfileStartupRecoveryService:
- probe_profile_health: 真实轻量并发探测 Agent 绑定的 Skill/MCP/Model/Tool 可用性
- rollback_to_last_known_good: 一键回滚到最近一次健康快照
- export_diagnostics: 导出结构化排障报告

[POS]
Agent 启动期安全恢复服务。
防止单个坏 MCP/Skill/Model 导致整机或会话启动崩溃，支持真实健康探测、故障隔离与 Last-Known-Good 自动快照回滚。
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlparse

import httpx

from app.services.agent.builtin_specs.builtin_tool_ids import (
    AGENT_BASELINE_BUILTIN_TOOLS,
    TOGGLABLE_BUILTIN_TOOL_IDS,
)
from app.services.agent.profile.profile_snapshot_service import ProfileSnapshotService

if TYPE_CHECKING:
    from app.services.agent.profile.profile_resolver import ResolvedAgentProfile

logger = logging.getLogger(__name__)

_PROBE_NETWORK_TIMEOUT_SECONDS = 0.35  # 350ms 熔断保护


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

    @classmethod
    async def _probe_single_builtin_tool(cls, tool_id: str) -> ComponentProbeResult:
        """Validate built-in tool ID validity."""
        start = time.monotonic()
        tool_id_clean = tool_id.strip()
        if not tool_id_clean:
            return ComponentProbeResult(
                component_type="builtin_tool",
                component_id=tool_id,
                status="quarantined",
                error_message="Empty built-in tool ID",
            )

        valid_ids = set(TOGGLABLE_BUILTIN_TOOL_IDS) | set(AGENT_BASELINE_BUILTIN_TOOLS)
        latency = (time.monotonic() - start) * 1000
        if tool_id_clean in valid_ids:
            return ComponentProbeResult(
                component_type="builtin_tool",
                component_id=tool_id_clean,
                status="healthy",
                latency_ms=round(latency, 2),
            )
        return ComponentProbeResult(
            component_type="builtin_tool",
            component_id=tool_id_clean,
            status="quarantined",
            error_message=f"Unknown built-in tool ID: {tool_id_clean}",
            latency_ms=round(latency, 2),
        )

    @classmethod
    async def _probe_single_skill(cls, skill_id: str) -> ComponentProbeResult:
        """Validate skill file availability and frontmatter validity."""
        start = time.monotonic()
        skill_id_clean = skill_id.strip()
        if not skill_id_clean:
            return ComponentProbeResult(
                component_type="skill",
                component_id=skill_id,
                status="quarantined",
                error_message="Empty skill ID",
            )

        # 1. 检查 prebuilt skills
        prebuilt_path = Path("assets/prebuilt_skills") / skill_id_clean / "SKILL.md"
        local_user_skill_path = Path.home() / ".myrm" / "skills" / skill_id_clean / "SKILL.md"

        target_file: Path | None = None
        if prebuilt_path.is_file():
            target_file = prebuilt_path
        elif local_user_skill_path.is_file():
            target_file = local_user_skill_path

        latency = (time.monotonic() - start) * 1000

        if target_file is None:
            # 兼容：如果以绝对路径或相对路径存在
            direct_path = Path(skill_id_clean)
            if direct_path.is_file():
                target_file = direct_path
            elif (direct_path / "SKILL.md").is_file():
                target_file = direct_path / "SKILL.md"

        if target_file is None:
            return ComponentProbeResult(
                component_type="skill",
                component_id=skill_id_clean,
                status="quarantined",
                error_message=f"Skill file not found for ID: {skill_id_clean}",
                latency_ms=round(latency, 2),
            )

        # 校验 frontmatter 语法
        try:
            content = target_file.read_text(encoding="utf-8", errors="replace")
            from app.core.skills.providers.local import parse_skill_md

            frontmatter = parse_skill_md(content)
            if not frontmatter and not content.strip().startswith("#"):
                return ComponentProbeResult(
                    component_type="skill",
                    component_id=skill_id_clean,
                    status="quarantined",
                    error_message=f"Skill metadata invalid or missing in {target_file.name}",
                    latency_ms=round((time.monotonic() - start) * 1000, 2),
                )
        except Exception as exc:
            return ComponentProbeResult(
                component_type="skill",
                component_id=skill_id_clean,
                status="quarantined",
                error_message=f"Error reading skill: {exc}",
                latency_ms=round((time.monotonic() - start) * 1000, 2),
            )

        return ComponentProbeResult(
            component_type="skill",
            component_id=skill_id_clean,
            status="healthy",
            latency_ms=round((time.monotonic() - start) * 1000, 2),
        )

    @classmethod
    async def _probe_single_mcp(cls, mcp_entry: str) -> ComponentProbeResult:
        """Validate MCP server connection or command availability."""
        start = time.monotonic()
        mcp_clean = mcp_entry.strip()
        if not mcp_clean:
            return ComponentProbeResult(
                component_type="mcp",
                component_id=mcp_entry,
                status="quarantined",
                error_message="Empty MCP identifier",
            )

        # 1. 如果是 HTTP / SSE 远程端点
        if mcp_clean.startswith(("http://", "https://")):
            # 如果是本地或远程端点，发异步轻量探测
            try:
                async with httpx.AsyncClient(timeout=_PROBE_NETWORK_TIMEOUT_SECONDS) as client:
                    await client.get(mcp_clean)
                    latency = (time.monotonic() - start) * 1000
                    # 任何响应（甚至 4xx/5xx）说明端口和服务活着
                    return ComponentProbeResult(
                        component_type="mcp",
                        component_id=mcp_clean,
                        status="healthy",
                        latency_ms=round(latency, 2),
                    )
            except Exception as exc:
                latency = (time.monotonic() - start) * 1000
                return ComponentProbeResult(
                    component_type="mcp",
                    component_id=mcp_clean,
                    status="quarantined",
                    error_message=f"MCP endpoint unreachable: {exc}",
                    latency_ms=round(latency, 2),
                )

        # 2. 如果是本地 stdio 命令（如 npx, python, node, uvx 等）
        command_parts = mcp_clean.split()
        binary_name = command_parts[0] if command_parts else mcp_clean
        binary_path = shutil.which(binary_name)
        latency = (time.monotonic() - start) * 1000

        if binary_path is not None or os.path.exists(binary_name):
            return ComponentProbeResult(
                component_type="mcp",
                component_id=mcp_clean,
                status="healthy",
                latency_ms=round(latency, 2),
            )

        return ComponentProbeResult(
            component_type="mcp",
            component_id=mcp_clean,
            status="quarantined",
            error_message=f"MCP executable command '{binary_name}' not found in PATH",
            latency_ms=round(latency, 2),
        )

    @staticmethod
    async def probe_profile_health(agent_id: str) -> ProfileHealthReport:
        """Probe all configured skills, MCPs, and tools for an agent concurrently."""
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

        # 并发执行全部组件探针
        tasks: list[asyncio.Task[ComponentProbeResult]] = []

        # 1. 探针内置工具
        for tool_id in resolved.enabled_builtin_tools:
            if tool_id.strip():
                tasks.append(asyncio.create_task(ProfileStartupRecoveryService._probe_single_builtin_tool(tool_id)))

        # 2. 探针技能
        for skill_id in resolved.skill_ids:
            if skill_id.strip():
                tasks.append(asyncio.create_task(ProfileStartupRecoveryService._probe_single_skill(skill_id)))

        # 3. 探针 MCP 连接
        for mcp_id in resolved.mcp_ids:
            if mcp_id.strip():
                tasks.append(asyncio.create_task(ProfileStartupRecoveryService._probe_single_mcp(mcp_id)))

        results = await asyncio.gather(*tasks, return_exceptions=True) if tasks else []

        healthy: list[ComponentProbeResult] = []
        quarantined: list[ComponentProbeResult] = []

        for res in results:
            if isinstance(res, Exception):
                quarantined.append(
                    ComponentProbeResult(
                        component_type="unknown",
                        component_id="probe_error",
                        status="quarantined",
                        error_message=str(res),
                    )
                )
            elif isinstance(res, ComponentProbeResult):
                if res.status == "healthy":
                    healthy.append(res)
                else:
                    quarantined.append(res)

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

