"""会话策略解析。

[POS]
channel_bridge 配置解析包的子模块；由 __init__.py 聚合导出。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.channels.types import SessionPolicy, SessionResetMode

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


_DEFAULT_SESSION_POLICY = SessionPolicy()


def extract_session_policy(
    personal_settings_dict: dict[str, object] | None,
) -> SessionPolicy:
    """Extract IM session reset policy from personalSettings.

    Expected JSON shape in personalSettings:
      { "sessionPolicy": { "mode": "daily", "dailyResetHour": 4, "idleMinutes": 120,
                            "notifyOnReset": true } }

    Returns DEFAULT_SESSION_POLICY when not configured.
    """
    if not personal_settings_dict:
        return _DEFAULT_SESSION_POLICY

    raw = personal_settings_dict.get("sessionPolicy")
    if not isinstance(raw, dict):
        return _DEFAULT_SESSION_POLICY

    try:
        mode = SessionResetMode(str(raw.get("mode", "daily")))
    except ValueError:
        mode = SessionResetMode.DAILY

    daily_hour = raw.get("dailyResetHour")
    idle_minutes = raw.get("idleMinutes")
    notify_raw = raw.get("notifyOnReset")

    return SessionPolicy(
        mode=mode,
        daily_reset_hour=int(daily_hour) if isinstance(daily_hour, (int, float)) else 4,
        idle_minutes=(int(idle_minutes) if isinstance(idle_minutes, (int, float)) else 120),
        notify_on_reset=bool(notify_raw) if notify_raw is not None else True,
    )


def session_policy_from_agent_dict(raw: dict[str, object]) -> SessionPolicy:
    """Build a SessionPolicy from a per-agent session_policy dict.

    Accepts the shape stored in agent metadata:
      { "mode": "daily", "daily_reset_hour": 4, "idle_minutes": 120,
        "notify_on_reset": true }
    """
    try:
        mode = SessionResetMode(str(raw.get("mode", "daily")))
    except ValueError:
        mode = SessionResetMode.DAILY

    daily_hour = raw.get("daily_reset_hour")
    idle_min = raw.get("idle_minutes")
    notify_raw = raw.get("notify_on_reset")
    return SessionPolicy(
        mode=mode,
        daily_reset_hour=int(daily_hour) if isinstance(daily_hour, (int, float)) else 4,
        idle_minutes=int(idle_min) if isinstance(idle_min, (int, float)) else 120,
        notify_on_reset=bool(notify_raw) if notify_raw is not None else True,
    )
