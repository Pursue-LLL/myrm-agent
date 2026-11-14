"""Browser Doctor — pre-flight diagnostics and health checks.

Validates dependencies, configuration, environment, and browser launchability
before actual operations. Provides clear fix suggestions for each failure.
Includes leftover process detection (browsers whose launching process is gone, read
from the ownership stamp) with safety mechanisms (dry-run default, force flag required
for cleanup), and the dry-run-first prune of stale automation sandboxes and stale
browser profile directories.

This package is the public facade for the doctor subdomain; it re-exports the
public symbols of the internal ``checks``, ``launch_check``, ``orphan_check``,
``orphans``, ``sandboxes``, ``profiles``, and ``report`` modules so that
``myrm_agent_harness.toolkits.browser.doctor`` remains a single import point.

[INPUT]
- .checks (POS: environment/dependency checks + run_doctor orchestrator)
- .launch_check (POS: bounded headless launch test)
- .orphan_check (POS: orphan process doctor check adapter)
- .orphans (POS: stamp-based leftover process detection and cleanup)
- .sandboxes (POS: stale automation sandbox cleanup)
- .profiles (POS: stale browser profile directory cleanup)
- .report (POS: doctor data models and CLI rendering)

[OUTPUT]
- run_doctor: pre-flight diagnostics orchestrator (re-export)
- check_memory / check_disk / check_browser_launch: individual checks reused outside the orchestrator (re-export)
- check_orphan_processes / cleanup_orphan_processes / find_orphan_automation_processes: orphan process utilities (re-export)
- cleanup_stale_automation_sandboxes: stale sandbox prune (re-export)
- cleanup_stale_browser_profiles: stale browser profile directory prune (re-export)
- OrphanProcess / OrphanCleanupResult / SandboxCleanupResult / ProfileCleanupResult: typed result shapes (re-export)
- CheckStatus / DoctorCheckResult / DoctorReport / format_report: report contract (re-export)

[POS]
Doctor subpackage public facade. Single import point aggregating the doctor
submodules for the harness CLI and server health endpoints.
"""

from __future__ import annotations

from .checks import check_disk, check_memory, run_doctor
from .launch_check import check_browser_launch
from .orphan_check import check_orphan_processes
from .orphans import (
    OrphanCleanupResult,
    OrphanProcess,
    cleanup_orphan_processes,
    find_orphan_automation_processes,
)
from .profiles import ProfileCleanupResult, cleanup_stale_browser_profiles
from .report import (
    CheckStatus,
    DoctorCheckResult,
    DoctorReport,
    format_report,
)
from .sandboxes import SandboxCleanupResult, cleanup_stale_automation_sandboxes

__all__ = [
    "CheckStatus",
    "DoctorCheckResult",
    "DoctorReport",
    "OrphanCleanupResult",
    "OrphanProcess",
    "ProfileCleanupResult",
    "SandboxCleanupResult",
    "check_browser_launch",
    "check_disk",
    "check_memory",
    "check_orphan_processes",
    "cleanup_orphan_processes",
    "cleanup_stale_automation_sandboxes",
    "cleanup_stale_browser_profiles",
    "find_orphan_automation_processes",
    "format_report",
    "run_doctor",
]
