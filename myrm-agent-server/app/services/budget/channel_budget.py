"""Per-channel budget quota enforcement and audit attribution.

[INPUT]
- myrm_agent_harness.utils.token_economics::DailyBudgetGuard (POS: Simple daily budget guard)
- myrm_agent_harness.utils.token_economics::BudgetStatus (POS: Budget status enum)
- app.database.models.chat::Chat, Message (POS: Session/message models)
- app.database.models.config::UserConfig (POS: User config persistence)
- app.services.budget.budget_day::budget_day_start_utc (POS: Budget day boundary as naive UTC)
- app.services.budget.channel_budget_key::normalize_channel_budget_key (POS: Canonical channel budget key)

[OUTPUT]
- ChannelBudgetPolicy: Per-channel budget configuration model; its key is always canonical
- ChannelBudgetRegistry: Process-scoped registry of per-channel DailyBudgetGuard instances
- load_channel_budget_policies: Load all channel policies from DB
- save_channel_budget_policy: Persist a single channel policy
- should_block_channel: Check if a specific channel should be blocked
- record_channel_cost: Record cost against a channel's budget guard
- ChannelBudgetPoliciesConfig: Aggregate config for all channel budget policies; policies of one canonical key are merged
- get_channel_budget_registry: Process-wide ChannelBudgetRegistry accessor
- delete_channel_budget_policy: Remove a single channel policy
- initialize_channel_budgets: Initialize the budget registry from the DB on startup

[POS]
Per-channel budget isolation for IM channels. Prevents a single busy channel
(e.g. a Slack group) from exhausting the owner's entire daily budget.
Reuses DailyBudgetGuard from harness layer for minimal code footprint.
"""

from __future__ import annotations

import logging
import threading
import uuid
from datetime import datetime
from typing import Self

from myrm_agent_harness.utils.token_economics.budget_guard import (
    BudgetStatus,
    DailyBudgetGuard,
)
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import and_, func, select

from app.database.models.chat import Chat, Message
from app.database.models.config import UserConfig
from app.database.repositories.channel_key_match import channel_key_extends
from app.platform_utils import get_session_factory
from app.services.budget.budget_day import budget_day_start_utc
from app.services.budget.channel_budget_key import normalize_channel_budget_key

logger = logging.getLogger(__name__)

CHANNEL_BUDGET_CONFIG_KEY = "channel_budget_policies"


class ChannelBudgetPolicy(BaseModel):
    """Per-channel daily budget configuration."""

    channel_key: str
    daily_limit_usd: float = Field(default=2.0, ge=0.01, le=10000.0)
    warning_threshold: float = Field(default=0.8, ge=0.1, le=1.0)
    enabled: bool = True
    label: str = ""

    @field_validator("channel_key", mode="before")
    @classmethod
    def _canonical_channel_key(cls, value: object) -> object:
        """Rows stored and keys typed in any spelling meet only the canonical key of a live message."""
        return normalize_channel_budget_key(value) if isinstance(value, str) else value


def _stricter(a: ChannelBudgetPolicy, b: ChannelBudgetPolicy) -> ChannelBudgetPolicy:
    """The enabled policy, then the one with the lower limit; ``a`` wins a tie."""
    if a.enabled != b.enabled:
        return a if a.enabled else b
    return b if b.daily_limit_usd < a.daily_limit_usd else a


class ChannelBudgetPoliciesConfig(BaseModel):
    """Aggregate config for all channel budget policies."""

    policies: list[ChannelBudgetPolicy] = Field(default_factory=list)

    @model_validator(mode="after")
    def _merge_colliding_keys(self) -> Self:
        """Policies whose keys canonicalise to one key are one policy; the stricter one is kept."""
        merged: dict[str, ChannelBudgetPolicy] = {}
        for policy in self.policies:
            kept = merged.get(policy.channel_key)
            if kept is not None:
                logger.warning("Channel budget policies collide on %s; keeping the stricter one", policy.channel_key)
            merged[policy.channel_key] = policy if kept is None else _stricter(kept, policy)
        if len(merged) < len(self.policies):
            self.policies = list(merged.values())
        return self


class ChannelBudgetRegistry:
    """Process-scoped registry of per-channel DailyBudgetGuard instances.

    Thread-safe via threading.Lock (matches MultidimensionalBudgetGuard pattern).
    Each channel budget key maps to an independent DailyBudgetGuard.
    """

    def __init__(self) -> None:
        self._guards: dict[str, DailyBudgetGuard] = {}
        self._policies: dict[str, ChannelBudgetPolicy] = {}
        self._lock = threading.Lock()

    def configure(self, policy: ChannelBudgetPolicy, initial_cost: float = 0.0) -> None:
        """Create or update a guard for the given channel key."""
        with self._lock:
            self._policies[policy.channel_key] = policy
            if policy.enabled:

                def _on_warning(cost: float, limit: float) -> None:
                    _emit_channel_budget_sse("warning", cost, limit, policy.channel_key)

                def _on_exceeded(cost: float, limit: float) -> None:
                    _emit_channel_budget_sse("exceeded", cost, limit, policy.channel_key)

                self._guards[policy.channel_key] = DailyBudgetGuard(
                    daily_budget_usd=policy.daily_limit_usd,
                    warning_threshold=policy.warning_threshold,
                    on_warning=_on_warning,
                    on_exceeded=_on_exceeded,
                    initial_cost=initial_cost,
                )
            else:
                self._guards.pop(policy.channel_key, None)

    def remove(self, channel_key: str) -> None:
        with self._lock:
            self._guards.pop(channel_key, None)
            self._policies.pop(channel_key, None)

    def check_budget(self, channel_key: str) -> BudgetStatus:
        """Check budget status for a channel. Returns OK if no guard configured."""
        with self._lock:
            guard = self._guards.get(channel_key)
            if guard is None:
                return BudgetStatus.OK
            return guard.check_budget(0.0)

    def record_cost(self, channel_key: str, cost: float) -> BudgetStatus:
        """Record cost against a channel guard. Returns OK if no guard configured."""
        with self._lock:
            guard = self._guards.get(channel_key)
            if guard is None:
                return BudgetStatus.OK
            return guard.record_cost(cost)

    def _build_status_dict(
        self,
        key: str,
        policy: ChannelBudgetPolicy,
        guard: DailyBudgetGuard | None,
    ) -> dict[str, object]:
        if guard is None:
            return {
                "channel_key": key,
                "label": policy.label,
                "enabled": False,
                "daily_limit_usd": round(policy.daily_limit_usd, 2),
                "today_cost_usd": 0.0,
                "remaining_usd": 0.0,
                "usage_pct": 0.0,
                "status": "disabled",
            }
        remaining = guard.get_remaining_budget() or 0.0
        today_cost = guard.today_cost
        limit = policy.daily_limit_usd
        return {
            "channel_key": key,
            "label": policy.label,
            "enabled": True,
            "daily_limit_usd": round(limit, 2),
            "today_cost_usd": round(today_cost, 6),
            "remaining_usd": round(remaining, 6),
            "usage_pct": round((today_cost / limit) * 100, 1) if limit > 0 else 0.0,
            "status": guard.check_budget(0.0).value,
        }

    def get_status(self, channel_key: str) -> dict[str, object] | None:
        """Get channel budget status. Returns None if no policy configured."""
        with self._lock:
            policy = self._policies.get(channel_key)
            if policy is None:
                return None
            return self._build_status_dict(channel_key, policy, self._guards.get(channel_key))

    def get_all_statuses(self) -> list[dict[str, object]]:
        with self._lock:
            return [self._build_status_dict(key, self._policies[key], self._guards.get(key)) for key in sorted(self._policies)]

    @property
    def policies(self) -> dict[str, ChannelBudgetPolicy]:
        with self._lock:
            return dict(self._policies)


_registry: ChannelBudgetRegistry | None = None


def get_channel_budget_registry() -> ChannelBudgetRegistry:
    global _registry
    if _registry is None:
        _registry = ChannelBudgetRegistry()
    return _registry


def _emit_channel_budget_sse(status: str, cost: float, limit: float, channel_key: str) -> None:
    """Emit SSE event for channel-specific budget alerts."""
    try:
        from app.services.event.app_event_bus import AppEvent, AppEventType, get_event_bus

        pct = round((cost / limit) * 100, 1) if limit > 0 else 100.0
        get_event_bus().publish(
            AppEvent(
                event_type=AppEventType.BUDGET_ALERT,
                data={
                    "subtype": "channel_budget_alert",
                    "status": status,
                    "dimension": "channel_daily",
                    "channel_key": channel_key,
                    "today_cost": round(cost, 6),
                    "daily_limit": round(limit, 6),
                    "remaining": round(max(0.0, limit - cost), 6),
                    "pct": pct,
                },
            )
        )
    except Exception as e:
        logger.warning("Failed to emit channel budget SSE alert: %s", e)


async def _query_channel_today_cost(channel_budget_key: str) -> float:
    """Sum the budget day's assistant costUsd across every chat of the group with this channel budget key."""
    try:
        session_factory = get_session_factory()
        today_start = budget_day_start_utc()
        cost_expr = func.json_extract(Message.extra_data, "$.costUsd")
        async with session_factory() as session:
            result = await session.execute(
                select(func.coalesce(func.sum(cost_expr), 0.0))
                .join(Chat, Message.chat_id == Chat.id)
                .where(
                    and_(
                        channel_key_extends(channel_budget_key),
                        Message.role == "assistant",
                        Message.extra_data.isnot(None),
                        Message.created_at >= today_start,
                        cost_expr.isnot(None),
                    )
                )
            )
            total: float = float(result.scalar_one())
        return total
    except Exception as e:
        logger.warning("Failed to recover channel cost from DB for %s: %s", channel_budget_key, e)
        return 0.0


async def load_channel_budget_policies() -> ChannelBudgetPoliciesConfig:
    """Load all channel budget policies from DB."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        result = await session.execute(select(UserConfig).where(UserConfig.config_key == CHANNEL_BUDGET_CONFIG_KEY))
        row = result.scalar_one_or_none()
        if row is None:
            return ChannelBudgetPoliciesConfig()
        try:
            return ChannelBudgetPoliciesConfig.model_validate(row.config_value)
        except Exception:
            logger.warning("Invalid channel budget policies in DB, returning defaults")
            return ChannelBudgetPoliciesConfig()


async def save_channel_budget_policy(policy: ChannelBudgetPolicy) -> None:
    """Save or update a single channel budget policy."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        result = await session.execute(select(UserConfig).where(UserConfig.config_key == CHANNEL_BUDGET_CONFIG_KEY))
        row = result.scalar_one_or_none()
        now_version = f"{int(datetime.now().timestamp() * 1000)}_0"

        if row is not None:
            config = ChannelBudgetPoliciesConfig.model_validate(row.config_value)
            existing = {p.channel_key: p for p in config.policies}
            existing[policy.channel_key] = policy
            config.policies = list(existing.values())
            row.config_value = config.model_dump()
            row.version = now_version
        else:
            config = ChannelBudgetPoliciesConfig(policies=[policy])
            new_config = UserConfig(
                id=str(uuid.uuid4()),
                config_key=CHANNEL_BUDGET_CONFIG_KEY,
                config_value=config.model_dump(),
                version=now_version,
                last_device_id="server",
                is_encrypted=False,
            )
            session.add(new_config)
        await session.commit()

    initial_cost = await _query_channel_today_cost(policy.channel_key)
    get_channel_budget_registry().configure(policy, initial_cost=initial_cost)


async def delete_channel_budget_policy(channel_key: str) -> bool:
    """Remove a channel budget policy; the key may be given in any spelling that canonicalises to the stored one."""
    key = normalize_channel_budget_key(channel_key)
    session_factory = get_session_factory()
    async with session_factory() as session:
        result = await session.execute(select(UserConfig).where(UserConfig.config_key == CHANNEL_BUDGET_CONFIG_KEY))
        row = result.scalar_one_or_none()
        if row is None:
            return False

        config = ChannelBudgetPoliciesConfig.model_validate(row.config_value)
        original_len = len(config.policies)
        config.policies = [p for p in config.policies if p.channel_key != key]
        if len(config.policies) == original_len:
            return False

        now_version = f"{int(datetime.now().timestamp() * 1000)}_0"
        row.config_value = config.model_dump()
        row.version = now_version
        await session.commit()

    get_channel_budget_registry().remove(key)
    return True


async def initialize_channel_budgets() -> None:
    """Initialize channel budget registry from DB on startup.

    Every stored policy is registered so listings show it; only an enabled policy gets a guard
    seeded with today's recovered spend, a disabled one has no guard and costs no query.
    """
    config = await load_channel_budget_policies()
    registry = get_channel_budget_registry()
    for policy in config.policies:
        initial_cost = await _query_channel_today_cost(policy.channel_key) if policy.enabled else 0.0
        registry.configure(policy, initial_cost=initial_cost)
        if initial_cost > 0:
            logger.info("Channel budget recovered for %s: $%.4f", policy.channel_key, initial_cost)


def should_block_channel(channel_budget_key: str) -> bool:
    """Check if a specific channel should be blocked due to budget exceeded.

    Fail-open: returns False if no guard configured or any error occurs.
    """
    try:
        status = get_channel_budget_registry().check_budget(channel_budget_key)
        return status == BudgetStatus.EXCEEDED
    except Exception:
        return False


def record_channel_cost(channel_budget_key: str, cost: float) -> None:
    """Record cost against a channel's budget guard (fire-and-forget)."""
    if cost <= 0:
        return
    try:
        get_channel_budget_registry().record_cost(channel_budget_key, cost)
    except Exception as e:
        logger.warning("Failed to record channel cost for %s: %s", channel_budget_key, e)
