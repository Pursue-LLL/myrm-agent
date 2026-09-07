"""Runtime meter service for search quota tracking, browser compute, and sandbox workload telemetry.

[INPUT]
- app.database.models.runtime_quota_metric::SearchQuotaRecord, BrowserRuntimeRecord, SandboxWorkloadRecord
- sqlalchemy.ext.asyncio::AsyncSession

[OUTPUT]
- RuntimeMeterService: Singleton service for recording and querying search quotas, browser compute, and sandbox workloads.

[POS]
Service layer for full-element operational cost meter: manages monthly search quotas with 429 self-healing,
browser compute duration, and sandbox execution workloads.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Final

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.runtime_quota_metric import (
    BrowserRuntimeRecord,
    SandboxWorkloadRecord,
    SearchQuotaRecord,
)

logger = logging.getLogger(__name__)

# Standard free monthly tier quotas by search provider
DEFAULT_SEARCH_QUOTA_BASELINES: Final[dict[str, int]] = {
    "tavily": 1000,
    "brave": 2000,
    "exa": 1000,
    "serpapi": 100,
    "searxng": 100000,  # Self-hosted open source baseline
    "bing": 1000,
    "google": 100,
}

UNMETERED_SEARCH_PROVIDERS: Final[frozenset[str]] = frozenset(
    {"searxng", "duckduckgo", "ddg"}
)

# Standard sandbox container compute rate ($0.001 / minute = $0.06 / hour)
ESTIMATED_COMPUTE_COST_PER_MINUTE_USD: Final[float] = 0.001


class RuntimeMeterService:
    """Service managing search quota ledgers and browser compute telemetry."""

    @staticmethod
    def get_current_year_month() -> str:
        """Return the current year-month in UTC as YYYY-MM."""
        return datetime.now(timezone.utc).strftime("%Y-%m")

    async def record_search_usage(
        self,
        session: AsyncSession,
        provider: str,
        count: int = 1,
        *,
        quota_exceeded: bool = False,
    ) -> SearchQuotaRecord:
        """Record search usage or apply 429 recalibration self-healing."""
        year_month = self.get_current_year_month()
        canonical_provider = provider.strip().lower()

        stmt = select(SearchQuotaRecord).where(
            SearchQuotaRecord.provider == canonical_provider,
            SearchQuotaRecord.year_month == year_month,
        )
        result = await session.execute(stmt)
        record = result.scalar_one_or_none()

        baseline = DEFAULT_SEARCH_QUOTA_BASELINES.get(canonical_provider, 1000)

        if record is None:
            # 优先从该 Provider 最近历史月份继承用户自定义的配额上限，防止月初自动降级回退默认基线
            inherited_stmt = (
                select(SearchQuotaRecord.quota_limit)
                .where(
                    SearchQuotaRecord.provider == canonical_provider,
                    SearchQuotaRecord.year_month != year_month,
                )
                .order_by(SearchQuotaRecord.year_month.desc())
                .limit(1)
            )
            inherited_res = await session.execute(inherited_stmt)
            inherited_limit = inherited_res.scalar_one_or_none()
            effective_limit = (
                inherited_limit if inherited_limit is not None else baseline
            )

            record = SearchQuotaRecord(
                provider=canonical_provider,
                year_month=year_month,
                used_count=count,
                quota_limit=effective_limit,
                is_depleted=quota_exceeded,
                last_depleted_at=datetime.now(timezone.utc) if quota_exceeded else None,
            )
            session.add(record)
        else:
            record.used_count += count
            if quota_exceeded:
                record.is_depleted = True
                record.last_depleted_at = datetime.now(timezone.utc)
                if record.used_count < record.quota_limit:
                    record.used_count = record.quota_limit
            elif record.used_count >= record.quota_limit:
                record.is_depleted = True

        try:
            await session.commit()
            await session.refresh(record)
        except Exception:
            await session.rollback()
            # Retry on concurrent insertion race condition
            stmt = select(SearchQuotaRecord).where(
                SearchQuotaRecord.provider == canonical_provider,
                SearchQuotaRecord.year_month == year_month,
            )
            result = await session.execute(stmt)
            record = result.scalar_one_or_none()
            if record is not None:
                record.used_count += count
                if quota_exceeded:
                    record.is_depleted = True
                    record.last_depleted_at = datetime.now(timezone.utc)
                    if record.used_count < record.quota_limit:
                        record.used_count = record.quota_limit
                elif record.used_count >= record.quota_limit:
                    record.is_depleted = True
                await session.commit()
                await session.refresh(record)
        return record

    async def get_search_quotas(self, session: AsyncSession) -> list[dict[str, object]]:
        """Query all search providers with their usage and depletion status."""
        year_month = self.get_current_year_month()

        stmt = select(SearchQuotaRecord).where(
            SearchQuotaRecord.year_month == year_month
        )
        result = await session.execute(stmt)
        records_by_provider = {rec.provider: rec for rec in result.scalars().all()}

        # 查询最近历史月份的上限字典，供当月尚未调用的 provider 优雅继承展示
        history_stmt = (
            select(SearchQuotaRecord.provider, SearchQuotaRecord.quota_limit)
            .where(SearchQuotaRecord.year_month != year_month)
            .order_by(SearchQuotaRecord.year_month.desc())
        )
        history_result = await session.execute(history_stmt)
        history_limits: dict[str, int] = {}
        for prov_name, q_limit in history_result.all():
            if prov_name not in history_limits:
                history_limits[prov_name] = q_limit

        output: list[dict[str, object]] = []

        all_providers = sorted(
            set(DEFAULT_SEARCH_QUOTA_BASELINES.keys()) | set(records_by_provider.keys())
        )
        for prov in all_providers:
            rec = records_by_provider.get(prov)
            fallback_limit = history_limits.get(
                prov, DEFAULT_SEARCH_QUOTA_BASELINES.get(prov, 1000)
            )
            limit = rec.quota_limit if rec is not None else fallback_limit
            used = rec.used_count if rec is not None else 0
            is_depleted = rec.is_depleted if rec is not None else False

            is_metered = prov not in UNMETERED_SEARCH_PROVIDERS
            ratio = min(1.0, used / limit) if limit > 0 else 1.0
            percentage = round(ratio * 100.0, 1)

            if is_depleted or (is_metered and used >= limit):
                status = "depleted"
            elif is_metered and ratio >= 0.95:
                status = "critical"
            elif is_metered and ratio >= 0.80:
                status = "warning"
            else:
                status = "healthy"

            output.append(
                {
                    "provider": prov,
                    "year_month": year_month,
                    "used_count": used,
                    "quota_limit": limit,
                    "remaining_count": max(0, limit - used) if is_metered else -1,
                    "percentage": percentage,
                    "is_metered": is_metered,
                    "is_depleted": is_depleted,
                    "status": status,
                    "last_depleted_at": (
                        rec.last_depleted_at.isoformat()
                        if rec and rec.last_depleted_at
                        else None
                    ),
                }
            )

        return output

    async def record_browser_runtime(
        self,
        session: AsyncSession,
        *,
        duration_seconds: float,
        active_compute_seconds: float,
        bytes_transferred: int,
        request_count: int,
        failed_request_count: int,
        session_id: str | None = None,
    ) -> BrowserRuntimeRecord:
        """Record session-level browser automation runtime telemetry."""
        year_month = self.get_current_year_month()
        record = BrowserRuntimeRecord(
            year_month=year_month,
            session_id=session_id,
            duration_seconds=max(0.0, duration_seconds),
            active_compute_seconds=max(0.0, active_compute_seconds),
            bytes_transferred=max(0, bytes_transferred),
            request_count=max(0, request_count),
            failed_request_count=max(0, failed_request_count),
        )
        session.add(record)
        await session.commit()
        await session.refresh(record)
        return record

    async def record_sandbox_workload(
        self,
        session: AsyncSession,
        *,
        workload_type: str = "code_sandbox",
        duration_seconds: float = 0.0,
        active_compute_seconds: float = 0.0,
        bytes_transferred: int = 0,
        execution_count: int = 1,
        failed_count: int = 0,
        session_id: str | None = None,
    ) -> SandboxWorkloadRecord:
        """Record session-level sandbox compute telemetry (code execution, bash, python)."""
        year_month = self.get_current_year_month()
        record = SandboxWorkloadRecord(
            year_month=year_month,
            workload_type=workload_type.strip().lower(),
            session_id=session_id,
            duration_seconds=max(0.0, duration_seconds),
            active_compute_seconds=max(0.0, active_compute_seconds),
            bytes_transferred=max(0, bytes_transferred),
            execution_count=max(1, execution_count),
            failed_count=max(0, failed_count),
        )
        session.add(record)
        await session.commit()
        await session.refresh(record)
        return record

    async def get_browser_runtime_summary(
        self, session: AsyncSession
    ) -> dict[str, object]:
        """Aggregate monthly browser and code sandbox compute duration and workload metrics."""
        year_month = self.get_current_year_month()

        stmt = select(
            func.count(BrowserRuntimeRecord.id).label("session_count"),
            func.coalesce(func.sum(BrowserRuntimeRecord.duration_seconds), 0.0).label(
                "total_duration_sec"
            ),
            func.coalesce(
                func.sum(BrowserRuntimeRecord.active_compute_seconds), 0.0
            ).label("total_compute_sec"),
            func.coalesce(func.sum(BrowserRuntimeRecord.bytes_transferred), 0).label(
                "total_bytes"
            ),
            func.coalesce(func.sum(BrowserRuntimeRecord.request_count), 0).label(
                "total_requests"
            ),
            func.coalesce(func.sum(BrowserRuntimeRecord.failed_request_count), 0).label(
                "total_failed_requests"
            ),
        ).where(BrowserRuntimeRecord.year_month == year_month)

        result = await session.execute(stmt)
        row = result.one()

        # Query sandbox workload metrics (code sandbox, bash execution)
        sandbox_stmt = select(
            func.count(SandboxWorkloadRecord.id).label("sandbox_count"),
            func.coalesce(func.sum(SandboxWorkloadRecord.duration_seconds), 0.0).label(
                "total_sandbox_duration_sec"
            ),
            func.coalesce(
                func.sum(SandboxWorkloadRecord.active_compute_seconds), 0.0
            ).label("total_sandbox_compute_sec"),
            func.coalesce(func.sum(SandboxWorkloadRecord.bytes_transferred), 0).label(
                "total_sandbox_bytes"
            ),
            func.coalesce(func.sum(SandboxWorkloadRecord.execution_count), 0).label(
                "total_executions"
            ),
            func.coalesce(func.sum(SandboxWorkloadRecord.failed_count), 0).label(
                "total_failed_executions"
            ),
        ).where(
            SandboxWorkloadRecord.year_month == year_month,
            SandboxWorkloadRecord.workload_type == "code_sandbox",
        )
        sandbox_result = await session.execute(sandbox_stmt)
        sandbox_row = sandbox_result.one()

        browser_duration_min = round(float(row.total_duration_sec) / 60.0, 2)
        browser_compute_min = round(float(row.total_compute_sec) / 60.0, 2)
        sandbox_compute_min = round(
            float(sandbox_row.total_sandbox_compute_sec) / 60.0, 2
        )
        total_active_compute_min = round(browser_compute_min + sandbox_compute_min, 2)

        total_bytes = int(row.total_bytes) + int(sandbox_row.total_sandbox_bytes)
        total_mb = round(float(total_bytes) / (1024.0 * 1024.0), 2)
        estimated_cost_usd = round(
            total_active_compute_min * ESTIMATED_COMPUTE_COST_PER_MINUTE_USD, 4
        )
        cloud_value_saved_usd = estimated_cost_usd  # 100% saved in local/desktop mode

        return {
            "year_month": year_month,
            "session_count": int(row.session_count) + int(sandbox_row.sandbox_count),
            "total_duration_minutes": browser_duration_min,
            "active_compute_minutes": browser_compute_min,
            "code_sandbox_compute_minutes": sandbox_compute_min,
            "total_active_compute_minutes": total_active_compute_min,
            "total_workload_active_minutes": total_active_compute_min,
            "code_sandbox_executions": int(sandbox_row.total_executions),
            "total_bytes_transferred": total_bytes,
            "total_megabytes_transferred": total_mb,
            "total_requests": int(row.total_requests),
            "total_failed_requests": int(row.total_failed_requests),
            "estimated_compute_cost_usd": estimated_cost_usd,
            "estimated_cloud_value_saved_usd": cloud_value_saved_usd,
            "is_local_mode": True,
        }

    async def reset_search_quota(
        self,
        session: AsyncSession,
        provider: str | None = None,
    ) -> int:
        """Reset search quota usage count and depletion status for one or all providers."""
        year_month = self.get_current_year_month()
        stmt = select(SearchQuotaRecord).where(
            SearchQuotaRecord.year_month == year_month
        )
        if provider is not None and provider.strip():
            stmt = stmt.where(SearchQuotaRecord.provider == provider.strip().lower())

        result = await session.execute(stmt)
        records = result.scalars().all()
        for rec in records:
            rec.used_count = 0
            rec.is_depleted = False
            rec.last_depleted_at = None

        await session.commit()
        return len(records)

    async def update_search_quota_limit(
        self,
        session: AsyncSession,
        provider: str,
        quota_limit: int,
    ) -> SearchQuotaRecord:
        """Update quota limit for a specific search provider."""
        year_month = self.get_current_year_month()
        canonical = provider.strip().lower()

        stmt = select(SearchQuotaRecord).where(
            SearchQuotaRecord.provider == canonical,
            SearchQuotaRecord.year_month == year_month,
        )
        result = await session.execute(stmt)
        record = result.scalar_one_or_none()

        limit = max(1, quota_limit)
        if record is None:
            record = SearchQuotaRecord(
                provider=canonical,
                year_month=year_month,
                used_count=0,
                quota_limit=limit,
                is_depleted=False,
            )
            session.add(record)
        else:
            record.quota_limit = limit
            if record.used_count < record.quota_limit:
                record.is_depleted = False

        await session.commit()
        await session.refresh(record)
        return record

    async def get_runtime_burn_rate_gauge(
        self, session: AsyncSession
    ) -> dict[str, object]:
        """Aggregate search quotas, browser compute, and operational burn rate warnings."""
        year_month = self.get_current_year_month()
        search_quotas = await self.get_search_quotas(session)
        browser_summary = await self.get_browser_runtime_summary(session)

        depleted = [
            item["provider"] for item in search_quotas if item.get("is_depleted")
        ]
        critical = [
            item["provider"]
            for item in search_quotas
            if item.get("status") == "critical"
        ]
        warning = [
            item["provider"]
            for item in search_quotas
            if item.get("status") == "warning"
        ]

        if depleted:
            overall_search_health = "critical"
        elif critical:
            overall_search_health = "warning"
        elif warning:
            overall_search_health = "warning"
        else:
            overall_search_health = "healthy"

        browser_cost = float(browser_summary.get("estimated_compute_cost_usd", 0.0))

        from app.services.observability.burn_rate_smoke_alarm import (
            smoke_alarm_detector,
        )

        smoke_verdict = smoke_alarm_detector.check_verdict()
        active_token_alerts = smoke_alarm_detector.get_active_alerts()

        is_burn_rate_alert = bool(
            depleted
            or len(critical) >= 2
            or browser_cost > 10.0
            or smoke_verdict.is_alert
        )

        if smoke_verdict.is_alert:
            message = f"Token burn rate smoke alarm triggered: {smoke_verdict.reason}"
        elif depleted:
            message = f"Search providers depleted: {', '.join(depleted)}. Auto-failover active."
        elif critical:
            message = (
                f"Search providers approaching limits: {', '.join(critical)} (>95%)."
            )
        elif browser_cost > 10.0:
            message = f"Browser compute cost (${browser_cost:.2f}) reached soft budget threshold."
        else:
            message = "All runtime search quotas, browser compute, and token burn rates operating within normal limits."

        return {
            "year_month": year_month,
            "overall_search_health": overall_search_health,
            "depleted_providers": depleted,
            "critical_providers": critical,
            "warning_providers": warning,
            "search_quotas": search_quotas,
            "browser_summary": browser_summary,
            "is_burn_rate_alert": is_burn_rate_alert,
            "burn_rate_message": message,
            "circuit_breakers": self.get_circuit_breaker_statuses(),
            "token_burn_rate": {
                "is_alert": smoke_verdict.is_alert,
                "tokens_per_minute": smoke_verdict.tokens_per_minute,
                "total_tokens_in_window": smoke_verdict.total_tokens_in_window,
                "active_alerts": active_token_alerts,
            },
        }

    def get_circuit_breaker_statuses(self) -> list[dict[str, object]]:
        """Retrieve telemetry snapshots of all active model/provider circuit breakers."""
        from myrm_agent_harness.toolkits.llms.fallback.circuit_breaker import (
            get_circuit_breaker_registry,
        )

        reg = get_circuit_breaker_registry()
        raw_stats = reg.get_all_stats()
        result: list[dict[str, object]] = []

        for key, stats in raw_stats.items():
            result.append(
                {
                    "key": key,
                    "state": str(stats.get("state", "closed")),
                    "failure_count": int(stats.get("failure_count", 0)),
                    "failure_threshold": int(stats.get("failure_threshold", 5)),
                    "timeout_ms": int(stats.get("timeout_ms", 30_000)),
                    "retry_after_ms": int(stats.get("retry_after_ms", 0)),
                    "is_open": stats.get("state") == "open",
                }
            )
        return result

    def reset_circuit_breaker(self, key: str | None = None) -> int:
        """Reset one or all registered circuit breakers to closed state."""
        from myrm_agent_harness.toolkits.llms.fallback.circuit_breaker import (
            get_circuit_breaker_registry,
        )

        reg = get_circuit_breaker_registry()
        if key:
            ok = reg.reset_one(key)
            return 1 if ok else 0
        return reg.reset_all()


runtime_meter_service = RuntimeMeterService()
