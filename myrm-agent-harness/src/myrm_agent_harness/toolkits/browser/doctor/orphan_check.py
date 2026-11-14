"""Browser Doctor — orphan process check adapter.

Turns the orphan process scan and the dry-run stale sandbox and stale browser profile
scans into one doctor check result, so ``orphans`` stays free of the report data model.

[INPUT]
- .orphans::find_orphan_automation_processes (POS: orphan process detection)
- .sandboxes::cleanup_stale_automation_sandboxes (POS: dry-run-first stale sandbox prune)
- .profiles::cleanup_stale_browser_profiles (POS: dry-run-first stale browser profile prune)
- .report::CheckStatus/DoctorCheckResult (POS: doctor data models)

[OUTPUT]
- check_orphan_processes: doctor check result for orphan automation processes, stale automation sandboxes and stale browser profiles

[POS]
Adapter between the orphan cleanup primitives and the doctor report model. The
scan walks the psutil process table synchronously, so callers offload it with
asyncio.to_thread.
"""

from __future__ import annotations

from .orphans import find_orphan_automation_processes
from .profiles import cleanup_stale_browser_profiles
from .report import CheckStatus, DoctorCheckResult
from .sandboxes import cleanup_stale_automation_sandboxes


def _megabytes(size_bytes: int) -> float:
    return round(size_bytes / (1024 * 1024), 1)


def check_orphan_processes() -> DoctorCheckResult:
    """Check for orphan automation browser processes, stale automation sandboxes and stale browser profiles."""
    orphans = find_orphan_automation_processes()
    sandbox_stat = cleanup_stale_automation_sandboxes(dry_run=True)
    stale_sandboxes = sandbox_stat.get("pruned", 0)
    stale_sandbox_bytes = sandbox_stat.get("reclaimed_bytes", 0)
    profile_stat = cleanup_stale_browser_profiles(dry_run=True)
    stale_profiles = profile_stat.get("pruned", 0)
    stale_profile_bytes = profile_stat.get("reclaimed_bytes", 0)
    stale_details = {
        "stale_sandboxes": stale_sandboxes,
        "stale_sandbox_bytes": stale_sandbox_bytes,
        "stale_profiles": stale_profiles,
        "stale_profile_bytes": stale_profile_bytes,
    }

    if not orphans and stale_sandboxes == 0 and stale_profiles == 0:
        return DoctorCheckResult(
            name="orphan_processes",
            status=CheckStatus.OK,
            message="No orphan automation processes, stale sandboxes or stale browser profiles detected",
            details={"count": 0, **stale_details},
        )

    msg_parts: list[str] = []
    if orphans:
        pids_preview: list[int | str] = [o["pid"] for o in orphans[:3]]
        if len(orphans) > 3:
            pids_preview.append("...")
        msg_parts.append(f"{len(orphans)} orphan automation process(es): {pids_preview}")
    if stale_sandboxes > 0:
        msg_parts.append(f"{stale_sandboxes} stale sandbox(es) ({_megabytes(stale_sandbox_bytes)} MB)")
    if stale_profiles > 0:
        msg_parts.append(f"{stale_profiles} stale browser profile(s) ({_megabytes(stale_profile_bytes)} MB)")

    return DoctorCheckResult(
        name="orphan_processes",
        status=CheckStatus.WARNING,
        message=f"Found {', '.join(msg_parts)}",
        fix="python -m myrm_agent_harness.toolkits.browser --cleanup-orphans --force",
        details={
            "count": len(orphans),
            "pids": [o["pid"] for o in orphans],
            "paths": [o["user_data_dir"] for o in orphans],
            **stale_details,
        },
    )
