"""Browser health checker implementation.

[INPUT]
- myrm_agent_harness.infra.health::HealthChecker (POS: 健康检查抽象基类)
- myrm_agent_harness.api::find_orphan_automation_processes (POS: 框架底层权威孤儿扫描)
- myrm_agent_harness.api::cleanup_orphan_processes (POS: 框架底层权威孤儿清理)

[OUTPUT]
- BrowserHealthChecker: 浏览器池健康检查和恢复

[POS]
浏览器健康检查器。通过委托 Harness 权威 orphans 内核，精准识别并清理脱钩的
Chromium 浏览器与 Node.js 驱动孤儿进程，彻底杜绝 Unix init (ppid=1) 漏报与个人 Chrome 误杀。
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

from myrm_agent_harness.api import (
    cleanup_orphan_processes,
    find_orphan_automation_processes,
)
from myrm_agent_harness.infra.health.health_checker import (
    HealthChecker,
    HealthCheckResult,
    HealthStatus,
    RecoveryResult,
    RecoveryStatus,
)

logger = logging.getLogger(__name__)


class BrowserHealthChecker(HealthChecker):
    """Health checker for browser pool.

    Checks for:
    - Orphan browser & driver processes (POSIX ppid re-parent safe + cache fingerprint matched)

    Recovery actions:
    - Terminate orphan browser & driver processes via Harness cleanup kernel
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
                message=f"Found {len(orphan_pids)} orphan browser/driver process(es)",
                details={"orphan_pids": orphan_pids[:10]},  # Limit to 10
            )

        return HealthCheckResult(
            status=HealthStatus.HEALTHY,
            message="No orphan browser processes found",
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
            await asyncio.sleep(0.5)

            remaining_orphans = await asyncio.to_thread(find_orphan_automation_processes)
            if remaining_orphans:
                remaining_pids = [int(p["pid"]) for p in remaining_orphans if "pid" in p]
                return RecoveryResult(
                    status=RecoveryStatus.PARTIAL,
                    message=f"Partial recovery: {killed_count} killed, {len(remaining_pids)} remain",
                    actions_taken=[f"Terminated {killed_count} orphan browser/driver process(es)"],
                    details={"remaining_orphans": remaining_pids[:5]},
                )

            return RecoveryResult(
                status=RecoveryStatus.SUCCESS,
                message=f"Recovery successful: terminated {killed_count} orphan process(es)",
                actions_taken=[f"Terminated {killed_count} orphan browser/driver process(es)"],
            )

        return RecoveryResult(
            status=RecoveryStatus.FAILED,
            message="Failed to terminate any orphan processes",
            actions_taken=["Attempted termination but failed"],
        )
