"""Browser health checker implementation.

[INPUT]
- myrm_agent_harness.infra.health::HealthChecker (POS: 健康检查抽象基类)

[OUTPUT]
- BrowserHealthChecker: 浏览器池健康检查和恢复

[POS]
浏览器健康检查器。检查孤儿浏览器进程（Chrome/Chromium），并尝试清理。
"""

from __future__ import annotations

import logging
import time
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

logger = logging.getLogger(__name__)

# Browser process names to check
BROWSER_PROCESS_NAMES = [
    "chrome",
    "chromium",
    "google-chrome",
    "chrome-sandbox",
    "chromium-browser",
]


class BrowserHealthChecker(HealthChecker):
    """Health checker for browser pool.

    Checks for:
    - Orphan browser processes (parent process is dead)

    Recovery actions:
    - Terminate orphan browser processes (SIGTERM)
    """

    async def check(self) -> HealthCheckResult:
        """Check browser pool health."""
        if not psutil:
            return HealthCheckResult(
                status=HealthStatus.UNKNOWN,
                message="psutil not available, cannot check browser processes",
            )

        orphan_pids = self._find_orphan_browser_processes()

        if orphan_pids:
            return HealthCheckResult(
                status=HealthStatus.UNHEALTHY,
                message=f"Found {len(orphan_pids)} orphan browser process(es)",
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

        orphan_pids = self._find_orphan_browser_processes()

        if not orphan_pids:
            return RecoveryResult(
                status=RecoveryStatus.SUCCESS,
                message="No orphan processes found",
                actions_taken=["No recovery actions needed"],
            )

        # Terminate orphan processes
        killed_count = self._terminate_processes(orphan_pids)

        if killed_count > 0:
            # Wait for processes to terminate
            time.sleep(1)

            # Verify recovery
            remaining_orphans = self._find_orphan_browser_processes()
            if remaining_orphans:
                return RecoveryResult(
                    status=RecoveryStatus.PARTIAL,
                    message=f"Partial recovery: {killed_count} killed, {len(remaining_orphans)} remain",
                    actions_taken=[f"Terminated {killed_count} orphan browser process(es)"],
                    details={"remaining_orphans": remaining_orphans[:5]},
                )

            return RecoveryResult(
                status=RecoveryStatus.SUCCESS,
                message=f"Recovery successful: terminated {killed_count} orphan process(es)",
                actions_taken=[f"Terminated {killed_count} orphan browser process(es)"],
            )

        return RecoveryResult(
            status=RecoveryStatus.FAILED,
            message="Failed to terminate any orphan processes",
            actions_taken=["Attempted termination but failed"],
        )

    def _find_orphan_browser_processes(self) -> list[int]:
        """Find orphan browser processes (parent process is dead)."""
        if not psutil:
            return []

        orphan_pids: list[int] = []

        for proc in psutil.process_iter(["pid", "name", "ppid"]):
            try:
                proc_info = proc.info
                proc_name = (proc_info.get("name") or "").lower()

                # Check if it's a browser process
                is_browser = any(name in proc_name for name in BROWSER_PROCESS_NAMES)
                if not is_browser:
                    continue

                # Check if parent process exists
                ppid = proc_info.get("ppid")
                if ppid:
                    try:
                        psutil.Process(ppid)
                        # Parent exists, not an orphan
                        continue
                    except psutil.NoSuchProcess:
                        # Parent is dead, this is an orphan
                        orphan_pids.append(proc.pid)
                else:
                    # No parent (ppid=0 or None), might be orphaned
                    orphan_pids.append(proc.pid)

            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass

        return orphan_pids

    def _terminate_processes(self, pids: list[int]) -> int:
        """Terminate processes by PIDs (SIGTERM first, then SIGKILL).

        Returns:
            Number of processes terminated
        """
        if not psutil:
            return 0

        killed_count = 0
        for pid in pids:
            try:
                proc = psutil.Process(pid)
                proc.terminate()  # SIGTERM
                logger.info(f"Sent SIGTERM to browser process {pid}")

                # Wait up to 5 seconds for process to terminate
                try:
                    proc.wait(timeout=5)
                    killed_count += 1
                    logger.info(f"Browser process {pid} terminated gracefully")
                except psutil.TimeoutExpired:
                    # Force kill if not terminated
                    proc.kill()  # SIGKILL
                    logger.warning(f"Force killed browser process {pid}")
                    killed_count += 1

            except psutil.NoSuchProcess:
                # Process already gone
                killed_count += 1
            except (psutil.AccessDenied, OSError) as err:
                logger.error(f"Failed to terminate browser process {pid}: {err}")

        return killed_count
