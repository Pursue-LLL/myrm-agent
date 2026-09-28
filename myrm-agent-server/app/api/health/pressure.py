"""User-facing resource pressure endpoint for the ResourcePressureBanner.

[INPUT]
- app.lifecycle.monitors::get_memory_pressure_monitor_instance (POS: harness memory pressure level)
- app.config.settings::settings (POS: state_dir for disk usage anchor)

[OUTPUT]
- router: GET /api/v1/health/pressure

[POS]
Reports memory pressure level (from the lifecycle-managed harness monitor)
and data-directory disk usage in one cheap call. Unauthenticated like the
rest of /health: contains only percentages and levels, no paths or secrets.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])

DISK_WARN_PERCENT = 85.0
DISK_CRITICAL_PERCENT = 95.0


def _memory_state() -> dict[str, object]:
    """Pull current memory level; unknown when the monitor is unavailable."""
    try:
        from app.lifecycle.monitors import get_memory_pressure_monitor_instance

        monitor = get_memory_pressure_monitor_instance()
        if monitor is None:
            return {"level": "unknown", "percent": None}
        return {
            "level": monitor.current_level.name.lower(),
            "percent": round(monitor.current_memory_percent, 1),
        }
    except Exception as exc:
        logger.warning("Memory pressure read failed: %s", exc)
        return {"level": "unknown", "percent": None}


def _disk_state(state_dir: str) -> dict[str, object]:
    """Disk usage of the data directory filesystem; unknown on any failure."""
    try:
        base = Path(state_dir).expanduser()
        anchor = base if base.exists() else base.parent
        total, _used, free = shutil.disk_usage(anchor)
        if total <= 0:
            return {"state": "unknown", "percent": None, "free_bytes": None}
        percent = round((total - free) / total * 100, 1)
        if percent >= DISK_CRITICAL_PERCENT:
            state = "critical"
        elif percent >= DISK_WARN_PERCENT:
            state = "elevated"
        else:
            state = "ok"
        return {"state": state, "percent": percent, "free_bytes": free}
    except Exception as exc:
        logger.warning("Disk usage read failed: %s", exc)
        return {"state": "unknown", "percent": None, "free_bytes": None}


@router.get("/pressure")
async def resource_pressure() -> dict[str, object]:
    """Memory + disk pressure snapshot for UI banners and cron gating."""
    from app.config.settings import get_settings

    settings = get_settings()
    return {
        "memory": _memory_state(),
        "disk": _disk_state(settings.database.state_dir),
        "thresholds": {
            "disk_warn_percent": DISK_WARN_PERCENT,
            "disk_critical_percent": DISK_CRITICAL_PERCENT,
        },
    }
