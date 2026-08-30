"""Browser health checker implementation.

[INPUT]
- myrm_agent_harness.infra.health::HealthChecker (POS: 健康检查抽象基类)
- myrm_agent_harness.toolkits.browser.doctor.orphans::find_orphan_automation_processes (POS: 权威孤儿进程识别)
- myrm_agent_harness.toolkits.browser.doctor.orphans::cleanup_orphan_processes (POS: 权威孤儿进程清理)

[OUTPUT]
- BrowserHealthChecker: 浏览器与驱动池健康检查和自愈恢复

[POS]
浏览器健康检查适配器。统一委托 Harness 权威内核，精准识别脱钩孤儿浏览器与 Node 驱动中继进程并完成自愈。
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

try:
    import psutil
except ImportError:
    psutil = None

from myrm_agent_harness.infra.health.health_checker import (
    HealthChecker,
    HealthCheckResult,
    HealthStatus,
    RecoveryResult,
    RecoveryStatus,
)
from myrm_agent_harness.toolkits.browser.doctor.orphans import (
    cleanup_orphan_processes,
    find_orphan_automation_processes,
)

logger = logging.getLogger(__name__)


class BrowserHealthChecker(HealthChecker):
    """Health checker for browser and driver automation pool.

    Checks for:
    - Orphan browser (Chromium) and driver (Node.js) processes (no living Python parent)

    Recovery actions:
    - Terminate orphan automation processes via Harness doctor engine
    """

    async def check(self) -> HealthCheckResult:
        """Check browser pool health."""
        if not psutil:
            return HealthCheckResult(
                status=HealthStatus.UNKNOWN,
                message="psutil not available, cannot check browser processes",
            )

        orphans = await asyncio.to_thread(find_orphan_automation_processes)

        if orphans:
            orphan_pids = [int(p["pid"]) for p in orphans if "pid" in p]
            return HealthCheckResult(
                status=HealthStatus.UNHEALTHY,
                message=f"Found {len(orphans)} orphan browser/driver process(es)",
                details={
                    "orphan_pids": orphan_pids[:10],
                    "total_count": len(orphans),
                },
            )

        return HealthCheckResult(
            status=HealthStatus.HEALTHY,
            message="No orphan browser or driver processes found",
        )

    async def recover(self) -> RecoveryResult:
        """Attempt to recover browser pool by terminating orphan processes."""
        if not psutil:
            return RecoveryResult(
                status=RecoveryStatus.NOT_ATTEMPTED,
                message="psutil not available, cannot recover",
                actions_taken=["No actions taken (psutil not available)"],
            )

        orphans = await asyncio.to_thread(find_orphan_automation_processes)

        if not orphans:
            return RecoveryResult(
                status=RecoveryStatus.SUCCESS,
                message="No orphan processes found",
                actions_taken=["No recovery actions needed"],
            )

        orphan_pids = [int(p["pid"]) for p in orphans if "pid" in p]
        result = await asyncio.to_thread(cleanup_orphan_processes, orphan_pids, force=True)

        killed_count = int(result.get("killed", 0))

        if killed_count > 0:
            # Yield control briefly to ensure OS updates process table
            await asyncio.sleep(0.5)

            # Verify recovery outcome
            remaining_orphans = await asyncio.to_thread(find_orphan_automation_processes)
            if remaining_orphans:
                remaining_pids = [int(p["pid"]) for p in remaining_orphans if "pid" in p]
                return RecoveryResult(
                    status=RecoveryStatus.PARTIAL,
                    message=f"Partial recovery: {killed_count} killed, {len(remaining_orphans)} remain",
                    actions_taken=[f"Terminated {killed_count} orphan process(es)"],
                    details={"remaining_orphans": remaining_pids[:5]},
                )

            return RecoveryResult(
                status=RecoveryStatus.SUCCESS,
                message=f"Recovery successful: terminated {killed_count} orphan process(es)",
                actions_taken=[f"Terminated {killed_count} orphan process(es)"],
            )

        return RecoveryResult(
            status=RecoveryStatus.FAILED,
            message="Failed to terminate any orphan processes",
            actions_taken=["Attempted termination but failed"],
        )
