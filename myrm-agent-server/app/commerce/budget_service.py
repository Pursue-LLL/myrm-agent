"""Commerce Budget Service for Autonomous Agent Spending.

[INPUT]
- myrm_agent_harness.core.security.egress.spend_governor::SpendGovernor, SpendGovernorConfig
- app.commerce.spending_ledger::SpendingLedgerEntry, SpendingLedgerStore, get_spending_ledger_store
- pydantic::BaseModel, Field

[OUTPUT]
- CommerceBudgetConfigDTO: 预算设置 DTO
- CommerceBudgetStatusDTO: 预算状态与指标 DTO
- CommerceBudgetService: 业务服务
- get_commerce_budget_service: 单例访问器

[POS]
Server-level commerce budget orchestrator coordinating SpendGovernor and persistent SpendingLedger.
"""

from __future__ import annotations

import logging
import os
import threading

from myrm_agent_harness.core.security.egress.spend_governor import (
    SpendGovernor,
    SpendGovernorConfig,
)
from pydantic import BaseModel, Field

from app.commerce.spending_ledger import (
    SpendingLedgerEntry,
    SpendingLedgerStore,
    get_spending_ledger_store,
)

logger = logging.getLogger(__name__)


class CommerceBudgetConfigDTO(BaseModel):
    """Configuration payload for autonomous commerce spending limits."""

    daily_cap_cents: int = Field(default=1000, ge=10, le=100000, description="Daily limit in USD Cents")
    per_action_cap_cents: int = Field(default=200, ge=10, le=5000, description="Per-action limit in USD Cents")
    allowed_merchants: list[str] = Field(
        default_factory=lambda: [
            "*.openai.com",
            "api.anthropic.com",
            "namesilo.com",
            "namecheap.com",
            "2captcha.com",
            "capsolver.com",
            "stripe.com",
        ],
        description="Allowed merchant domain patterns",
    )
    currency: str = Field(default="USD", description="Currency ISO code")
    is_frozen: bool = Field(default=False, description="Emergency circuit breaker state")
    lease_ttl_seconds: int = Field(default=120, ge=10, le=600, description="Reservation lease TTL")


class CommerceBudgetStatusDTO(BaseModel):
    """Live status and real-time metrics for autonomous commerce budget."""

    daily_cap_cents: int
    per_action_cap_cents: int
    daily_spent_cents: int
    active_reserved_cents: int
    remaining_cents: int
    currency: str
    is_frozen: bool
    allowed_merchants: list[str]
    total_leases_tracked: int


class PreAuthResultDTO(BaseModel):
    """Result of requesting a pre-authorized spend voucher."""

    success: bool
    code: str
    message: str
    lease_id: str | None = None
    voucher: str | None = None
    amount_cents: int = 0
    merchant_domain: str = ""
    expires_at: float | None = None


class CommerceBudgetService:
    """Orchestrates in-memory SpendGovernor state machine with persistent SpendingLedger."""

    def __init__(
        self,
        governor: SpendGovernor | None = None,
        ledger_store: SpendingLedgerStore | None = None,
    ) -> None:
        self._governor = governor or SpendGovernor()
        self._ledger = ledger_store or get_spending_ledger_store()
        self._lock = threading.Lock()

    def get_status(self) -> CommerceBudgetStatusDTO:
        """Fetch current budget caps and real-time spend metrics."""
        with self._lock:
            metrics = self._governor.get_metrics()
            return CommerceBudgetStatusDTO(
                daily_cap_cents=int(metrics["dailyCapCents"]),  # type: ignore[arg-type]
                per_action_cap_cents=int(metrics["perActionCapCents"]),  # type: ignore[arg-type]
                daily_spent_cents=int(metrics["dailySpentCents"]),  # type: ignore[arg-type]
                active_reserved_cents=int(metrics["activeReservedCents"]),  # type: ignore[arg-type]
                remaining_cents=int(metrics["remainingCents"]),  # type: ignore[arg-type]
                currency=str(metrics["currency"]),
                is_frozen=bool(metrics["isFrozen"]),
                allowed_merchants=list(metrics["allowedMerchants"]),  # type: ignore[arg-type]
                total_leases_tracked=int(metrics["totalLeasesTracked"]),  # type: ignore[arg-type]
            )

    def update_config(self, config: CommerceBudgetConfigDTO) -> CommerceBudgetStatusDTO:
        """Update spending limits and merchant domain whitelist."""
        with self._lock:
            new_governor_config = SpendGovernorConfig(
                daily_cap_cents=config.daily_cap_cents,
                per_action_cap_cents=config.per_action_cap_cents,
                allowed_merchants=tuple(config.allowed_merchants),
                currency=config.currency,
                is_frozen=config.is_frozen,
                lease_ttl_seconds=config.lease_ttl_seconds,
            )
            self._governor.update_config(new_governor_config)
            return self.get_status()

    def set_freeze(self, freeze: bool) -> CommerceBudgetStatusDTO:
        """Trigger or release emergency freeze circuit breaker."""
        with self._lock:
            if freeze:
                self._governor.freeze()
            else:
                self._governor.unfreeze()
            return self.get_status()

    def pre_authorize_spend(
        self,
        merchant_domain: str,
        amount_cents: int,
        session_id: str = "global",
        task_id: str | None = None,
        idempotency_key: str = "",
    ) -> PreAuthResultDTO:
        """Reserve a spending lease and create a persistent ledger entry."""
        with self._lock:
            result = self._governor.reserve(
                merchant_domain=merchant_domain,
                amount_cents=amount_cents,
                idempotency_key=idempotency_key,
            )
            if not result.success or not result.lease:
                return PreAuthResultDTO(
                    success=False,
                    code=result.code,
                    message=result.message,
                    amount_cents=amount_cents,
                    merchant_domain=merchant_domain,
                )

            # Record in persistent ledger
            entry = SpendingLedgerEntry(
                entry_id=f"entry_{os.urandom(8).hex()}",
                lease_id=result.lease.lease_id,
                session_id=session_id,
                task_id=task_id,
                merchant_domain=result.lease.merchant_domain,
                amount_cents=result.lease.amount_cents,
                currency=result.lease.currency,
                status="reserved",
                idempotency_key=idempotency_key,
            )
            self._ledger.record_entry(entry)

            return PreAuthResultDTO(
                success=True,
                code="APPROVED",
                message=result.message,
                lease_id=result.lease.lease_id,
                voucher=result.voucher,
                amount_cents=result.lease.amount_cents,
                merchant_domain=result.lease.merchant_domain,
                expires_at=result.lease.expires_at,
            )

    def commit_spend(
        self,
        lease_id: str,
        idempotency_key: str = "",
    ) -> dict[str, object]:
        """Commit an approved spend lease and finalize ledger entry."""
        with self._lock:
            res = self._governor.commit(lease_id=lease_id, idempotency_key=idempotency_key)
            if not res.success:
                if res.code == "LEASE_EXPIRED":
                    self._ledger.update_status(lease_id, "rejected")
                return {"success": False, "code": res.code, "message": res.message}

            # Update persistent ledger
            self._ledger.update_status(
                lease_id=lease_id,
                status="committed",
                entry_hash=res.entry_hash,
                action_digest=res.action_digest,
            )
            return {
                "success": True,
                "code": res.code,
                "message": res.message,
                "entryHash": res.entry_hash,
                "actionDigest": res.action_digest,
            }

    def release_spend(self, lease_id: str) -> bool:
        """Release a reserved spend lease and mark refunded in ledger."""
        with self._lock:
            released = self._governor.release(lease_id)
            if released:
                self._ledger.update_status(lease_id, "refunded")
            return released

    def list_ledger_entries(
        self,
        session_id: str | None = None,
        limit: int = 50,
    ) -> list[SpendingLedgerEntry]:
        """Fetch audit log entries."""
        return self._ledger.list_entries(session_id=session_id, limit=limit)


_GLOBAL_COMMERCE_BUDGET_SERVICE: CommerceBudgetService | None = None
_SERVICE_LOCK = threading.Lock()


def get_commerce_budget_service() -> CommerceBudgetService:
    """Get singleton commerce budget service."""
    global _GLOBAL_COMMERCE_BUDGET_SERVICE
    with _SERVICE_LOCK:
        if _GLOBAL_COMMERCE_BUDGET_SERVICE is None:
            _GLOBAL_COMMERCE_BUDGET_SERVICE = CommerceBudgetService()
        return _GLOBAL_COMMERCE_BUDGET_SERVICE
