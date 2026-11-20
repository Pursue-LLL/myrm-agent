"""Per-channel budget policy models: one policy, a patch of one, and the stored aggregate.

[INPUT]
- app.services.budget.channel_budget_key::normalize_channel_budget_key (POS: Canonical channel budget key)

[OUTPUT]
- ChannelBudgetPolicy: Per-channel budget configuration model; its key is always canonical
- ChannelBudgetPolicyPatch: The fields of a stored policy to change; fields left out keep their stored values
- ChannelBudgetPoliciesConfig: Aggregate config for all channel budget policies; policies of one canonical key are merged

[POS]
The shape of what the channel budget store holds and the budget API accepts, kept apart from the registry that enforces
the policies and the persistence that reads and writes them.
"""

from __future__ import annotations

import logging
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.services.budget.channel_budget_key import normalize_channel_budget_key

logger = logging.getLogger(__name__)


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


class ChannelBudgetPolicyPatch(BaseModel):
    """The fields of a stored policy to change; the merged policy is validated like a saved one."""

    model_config = ConfigDict(extra="forbid")

    daily_limit_usd: float | None = None
    warning_threshold: float | None = None
    enabled: bool | None = None
    label: str | None = None


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
