"""Runtime meter service for search quota tracking and browser compute telemetry.

[INPUT]
- app.database.models.runtime_quota_metric::SearchQuotaRecord, BrowserRuntimeRecord
- sqlalchemy.ext.asyncio::AsyncSession

[OUTPUT]
- RuntimeMeterService: Singleton service for recording and querying search quotas and browser compute.

[POS]
Service layer for full-element operational cost meter: manages monthly search quotas with 429 self-healing
and records browser compute duration and network transfer volume.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Final

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.runtime_quota_metric import BrowserRuntimeRecord, SearchQuotaRecord

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

UNMETERED_SEARCH_PROVIDERS: Final[frozenset[str]] = frozenset({"searxng", "duckduckgo", "ddg"})

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
            record = SearchQuotaRecord(
                provider=canonical_provider,
                year_month=year_month,
                used_count=count,
                quota_limit=baseline,
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

        stmt = select(SearchQuotaRecord).where(SearchQuotaRecord.year_month == year_month)
        result = await session.execute(stmt)
        records_by_provider = {rec.provider: rec for rec in result.scalars().all()}

        output: list[dict[str, object]] = []

        all_providers = sorted(set(DEFAULT_SEARCH_QUOTA_BASELINES.keys()) | set(records_by_provider.keys()))
        for prov in all_providers:
            rec = records_by_provider.get(prov)
            limit = rec.quota_limit if rec is not None else DEFAULT_SEARCH_QUOTA_BASELINES.get(prov, 1000)
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
                    "last_depleted_at": rec.last_depleted_at.isoformat() if rec and rec.last_depleted_at else None,
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

    async def get_browser_runtime_summary(self, session: AsyncSession) -> dict[str, object]:
        """Aggregate monthly browser compute duration and bandwidth consumption."""
        year_month = self.get_current_year_month()

        stmt = select(
            func.count(BrowserRuntimeRecord.id).label("session_count"),
            func.coalesce(func.sum(BrowserRuntimeRecord.duration_seconds), 0.0).label("total_duration_sec"),
            func.coalesce(func.sum(BrowserRuntimeRecord.active_compute_seconds), 0.0).label("total_compute_sec"),
            func.coalesce(func.sum(BrowserRuntimeRecord.bytes_transferred), 0).label("total_bytes"),
            func.coalesce(func.sum(BrowserRuntimeRecord.request_count), 0).label("total_requests"),
            func.coalesce(func.sum(BrowserRuntimeRecord.failed_request_count), 0).label("total_failed_requests"),
        ).where(BrowserRuntimeRecord.year_month == year_month)

        result = await session.execute(stmt)
        row = result.one()

        total_duration_min = round(float(row.total_duration_sec) / 60.0, 2)
        total_compute_min = round(float(row.total_compute_sec) / 60.0, 2)
        total_mb = round(float(row.total_bytes) / (1024.0 * 1024.0), 2)
        estimated_cost_usd = round(total_compute_min * ESTIMATED_COMPUTE_COST_PER_MINUTE_USD, 4)

        return {
            "year_month": year_month,
            "session_count": int(row.session_count),
            "total_duration_minutes": total_duration_min,
            "active_compute_minutes": total_compute_min,
            "total_bytes_transferred": int(row.total_bytes),
            "total_megabytes_transferred": total_mb,
            "total_requests": int(row.total_requests),
            "total_failed_requests": int(row.total_failed_requests),
            "estimated_compute_cost_usd": estimated_cost_usd,
        }

    async def reset_search_quota(
        self,
        session: AsyncSession,
        provider: str | None = None,
    ) -> int:
        """Reset search quota usage count and depletion status for one or all providers."""
        year_month = self.get_current_year_month()
        stmt = select(SearchQuotaRecord).where(SearchQuotaRecord.year_month == year_month)
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

    async def get_runtime_burn_rate_gauge(self, session: AsyncSession) -> dict[str, object]:
        """Aggregate search quotas, browser compute, and operational burn rate warnings."""
        year_month = self.get_current_year_month()
        search_quotas = await self.get_search_quotas(session)
        browser_summary = await self.get_browser_runtime_summary(session)

        depleted = [item["provider"] for item in search_quotas if item.get("is_depleted")]
        critical = [item["provider"] for item in search_quotas if item.get("status") == "critical"]
        warning = [item["provider"] for item in search_quotas if item.get("status") == "warning"]

        if depleted:
            overall_search_health = "critical"
        elif critical:
            overall_search_health = "warning"
        elif warning:
            overall_search_health = "warning"
        else:
            overall_search_health = "healthy"

        browser_cost = float(browser_summary.get("estimated_compute_cost_usd", 0.0))
        is_burn_rate_alert = bool(depleted or len(critical) >= 2 or browser_cost > 10.0)

        if depleted:
            message = f"Search providers depleted: {', '.join(depleted)}. Auto-failover active."
        elif critical:
            message = f"Search providers approaching limits: {', '.join(critical)} (>95%)."
        elif browser_cost > 10.0:
            message = f"Browser compute cost (${browser_cost:.2f}) reached soft budget threshold."
        else:
            message = "All runtime search quotas and browser compute operating within normal limits."

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
        }


runtime_meter_service = RuntimeMeterService()
