"""Memory guardian policy persistence and schedule helpers.

[INPUT]
- app.database.models.config::UserConfig (POS: single-user config storage)
- app.platform_utils::get_session_factory (POS: async DB session factory)

[OUTPUT]
- MemoryGuardianPolicy: persisted policy schema for frequency tier / quiet window.
- load_memory_guardian_policy: load policy from UserConfig with safe defaults.
- save_memory_guardian_policy: persist policy and return canonical model.
- resolve_guardian_intervals / is_within_quiet_window / seconds_until_quiet_window_open:
  runtime helpers used by lifecycle scheduler and API status projection.

[POS]
Memory Guardian policy service. Owns constrained user-configurable scheduling knobs
without coupling UI persistence logic into lifecycle runtime code.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.database.models.config import UserConfig
from app.platform_utils import get_session_factory

MEMORY_GUARDIAN_POLICY_CONFIG_KEY = "memory_guardian_policy"

MemoryGuardianFrequencyTier = Literal["conservative", "balanced", "aggressive"]
MemoryGuardianTimezoneSource = Literal["unknown", "client_header", "server_fallback", "manual"]


@dataclass(frozen=True, slots=True)
class GuardianIntervalProfile:
    healthy_hours: int
    unhealthy_hours: int


_FREQUENCY_INTERVALS: dict[MemoryGuardianFrequencyTier, GuardianIntervalProfile] = {
    "conservative": GuardianIntervalProfile(healthy_hours=8, unhealthy_hours=4),
    "balanced": GuardianIntervalProfile(healthy_hours=6, unhealthy_hours=2),
    "aggressive": GuardianIntervalProfile(healthy_hours=4, unhealthy_hours=1),
}


class MemoryGuardianPolicy(BaseModel):
    """User-configurable guardian policy persisted in UserConfig."""

    frequency_tier: MemoryGuardianFrequencyTier = "balanced"
    quiet_window_enabled: bool = False
    quiet_window_start_hour: int = Field(default=0, ge=0, le=23)
    quiet_window_end_hour: int = Field(default=6, ge=0, le=23)
    timezone_offset_minutes: int = Field(default=0, ge=-720, le=840)
    timezone_initialized: bool = False
    timezone_source: MemoryGuardianTimezoneSource = "unknown"

    @model_validator(mode="after")
    def _validate_quiet_window(self) -> "MemoryGuardianPolicy":
        if self.quiet_window_enabled and self.quiet_window_start_hour == self.quiet_window_end_hour:
            raise ValueError("quiet window start/end hour cannot be identical when quiet window is enabled")
        return self


def resolve_guardian_intervals(policy: MemoryGuardianPolicy) -> GuardianIntervalProfile:
    """Resolve adaptive healthy/unhealthy interval profile from frequency tier."""
    return _FREQUENCY_INTERVALS[policy.frequency_tier]


def current_local_hour(*, policy: MemoryGuardianPolicy, now_ts: float | None = None) -> int:
    """Return policy-local clock hour in [0, 23] based on fixed UTC offset."""
    second_of_day = _local_second_of_day(policy=policy, now_ts=now_ts)
    return second_of_day // 3600


def is_within_quiet_window(*, policy: MemoryGuardianPolicy, now_ts: float | None = None) -> bool:
    """Return True when current policy-local time is inside configured quiet window."""
    if not policy.quiet_window_enabled:
        return True
    second_of_day = _local_second_of_day(policy=policy, now_ts=now_ts)
    start_sec = policy.quiet_window_start_hour * 3600
    end_sec = policy.quiet_window_end_hour * 3600
    if start_sec < end_sec:
        return start_sec <= second_of_day < end_sec
    return second_of_day >= start_sec or second_of_day < end_sec


def seconds_until_quiet_window_open(*, policy: MemoryGuardianPolicy, now_ts: float | None = None) -> int:
    """Return seconds until next quiet-window opening; 0 when already in window."""
    if not policy.quiet_window_enabled:
        return 0
    if is_within_quiet_window(policy=policy, now_ts=now_ts):
        return 0

    second_of_day = _local_second_of_day(policy=policy, now_ts=now_ts)
    start_sec = policy.quiet_window_start_hour * 3600

    delta = start_sec - second_of_day
    if delta < 0:
        delta += 24 * 3600
    return delta


async def load_memory_guardian_policy() -> MemoryGuardianPolicy:
    """Load memory guardian policy from UserConfig; return defaults when absent/invalid."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        result = await session.execute(
            select(UserConfig).where(UserConfig.config_key == MEMORY_GUARDIAN_POLICY_CONFIG_KEY)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return MemoryGuardianPolicy()
        try:
            return MemoryGuardianPolicy.model_validate(row.config_value)
        except Exception:
            return MemoryGuardianPolicy()


async def save_memory_guardian_policy(policy: MemoryGuardianPolicy) -> MemoryGuardianPolicy:
    """Persist memory guardian policy and return canonical model."""
    canonical_policy = policy.model_copy(update={"timezone_initialized": True, "timezone_source": "manual"})
    session_factory = get_session_factory()
    async with session_factory() as session:
        result = await session.execute(
            select(UserConfig).where(UserConfig.config_key == MEMORY_GUARDIAN_POLICY_CONFIG_KEY)
        )
        row = result.scalar_one_or_none()
        now_version = f"{int(datetime.now().timestamp() * 1000)}_0"
        if row is None:
            row = UserConfig(
                id=uuid.uuid4().hex,
                config_key=MEMORY_GUARDIAN_POLICY_CONFIG_KEY,
                config_value=canonical_policy.model_dump(),
                version=now_version,
                last_device_id="server",
                is_encrypted=False,
            )
            session.add(row)
        else:
            row.config_value = canonical_policy.model_dump()  # type: ignore[assignment]
            row.version = now_version
        await session.commit()
    return canonical_policy


async def ensure_memory_guardian_timezone_initialized(
    offset_minutes: int,
    *,
    source: Literal["client_header", "server_fallback"] = "client_header",
) -> MemoryGuardianPolicy:
    """Initialize guardian timezone and allow trusted client headers to correct fallback defaults."""
    normalized_offset = max(-720, min(840, int(offset_minutes)))
    session_factory = get_session_factory()
    async with session_factory() as session:
        result = await session.execute(
            select(UserConfig).where(UserConfig.config_key == MEMORY_GUARDIAN_POLICY_CONFIG_KEY)
        )
        row = result.scalar_one_or_none()
        now_version = f"{int(datetime.now().timestamp() * 1000)}_0"
        if row is None:
            initialized = MemoryGuardianPolicy(
                timezone_offset_minutes=normalized_offset,
                timezone_initialized=True,
                timezone_source=source,
            )
            row = UserConfig(
                id=uuid.uuid4().hex,
                config_key=MEMORY_GUARDIAN_POLICY_CONFIG_KEY,
                config_value=initialized.model_dump(),
                version=now_version,
                last_device_id="server",
                is_encrypted=False,
            )
            session.add(row)
            try:
                await session.commit()
                return initialized
            except IntegrityError:
                await session.rollback()
                refresh = await session.execute(
                    select(UserConfig).where(UserConfig.config_key == MEMORY_GUARDIAN_POLICY_CONFIG_KEY)
                )
                merged_row = refresh.scalar_one_or_none()
                if merged_row is None:
                    return initialized
                try:
                    return MemoryGuardianPolicy.model_validate(merged_row.config_value)
                except Exception:
                    return MemoryGuardianPolicy(
                        timezone_offset_minutes=normalized_offset,
                        timezone_initialized=True,
                        timezone_source=source,
                    )

        try:
            existing = MemoryGuardianPolicy.model_validate(row.config_value)
        except Exception:
            existing = MemoryGuardianPolicy()

        if existing.timezone_initialized:
            if (
                source == "client_header"
                and existing.timezone_source == "server_fallback"
                and existing.timezone_offset_minutes != normalized_offset
            ):
                corrected = existing.model_copy(
                    update={
                        "timezone_offset_minutes": normalized_offset,
                        "timezone_source": "client_header",
                    }
                )
                row.config_value = corrected.model_dump()  # type: ignore[assignment]
                row.version = now_version
                await session.commit()
                return corrected
            return existing

        if existing.timezone_offset_minutes == 0:
            initialized = existing.model_copy(
                update={
                    "timezone_offset_minutes": normalized_offset,
                    "timezone_initialized": True,
                    "timezone_source": source,
                }
            )
        else:
            initialized = existing.model_copy(
                update={
                    "timezone_initialized": True,
                    "timezone_source": source,
                }
            )
        row.config_value = initialized.model_dump()  # type: ignore[assignment]
        row.version = now_version
        await session.commit()
        return initialized


def _local_second_of_day(*, policy: MemoryGuardianPolicy, now_ts: float | None = None) -> int:
    ts = now_ts if now_ts is not None else time.time()
    local_ts = int(ts + policy.timezone_offset_minutes * 60)
    return local_ts % (24 * 3600)
