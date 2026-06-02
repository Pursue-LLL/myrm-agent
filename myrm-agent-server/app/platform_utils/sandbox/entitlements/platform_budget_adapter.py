"""Control Plane Work Unit budget adapter for sandbox deployments."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from concurrent.futures import ThreadPoolExecutor
from typing import TypeVar

import httpx
from myrm_agent_harness.utils.token_economics.budget_guard import BudgetStatus

from app.config.settings import settings

logger = logging.getLogger(__name__)

_REQUEST_TIMEOUT: float = 5.0

T = TypeVar("T")

_async_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="cp-budget-http")


def _run_async(coro: Coroutine[object, object, T]) -> T:
    """Run an async coroutine from sync BudgetChecker hooks."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    future = _async_executor.submit(asyncio.run, coro)
    return future.result(timeout=_REQUEST_TIMEOUT + 2.0)


class PlatformBudgetAdapter:
    """Implements BudgetChecker by reserving/committing Work Units via Control Plane."""

    def __init__(self) -> None:
        cp = settings.control_plane
        self._base_url = cp.url.strip().rstrip("/")
        self._token = cp.telemetry_token.get_secret_value()
        self._sandbox_id = cp.sandbox_id
        self._wu_per_usd = cp.platform_wu_per_usd
        self._remaining_wu: int = 0
        self._active_reservation_id: str | None = None
        self._reserved_wu: int = 0
        self._client: httpx.AsyncClient | None = None
        self._configured = bool(self._base_url and self._token and self._sandbox_id)
        if not self._configured:
            logger.warning("PlatformBudgetAdapter disabled: missing CONTROL_PLANE_URL, token, or SANDBOX_ID")
        else:
            self._refresh_balance_sync()

    @property
    def is_configured(self) -> bool:
        return self._configured

    def _headers(self) -> dict[str, str]:
        return {
            "X-Telemetry-Token": self._token,
            "X-Sandbox-Id": self._sandbox_id,
            "Content-Type": "application/json",
        }

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=_REQUEST_TIMEOUT)
        return self._client

    def _usd_to_wu(self, cost_usd: float) -> int:
        if cost_usd <= 0:
            return 1
        return max(1, int(cost_usd * self._wu_per_usd))

    async def _refresh_balance_async(self) -> None:
        if not self._configured:
            return
        try:
            client = self._get_client()
            response = await client.get(
                f"{self._base_url}/api/internal/billing/balance",
                headers=self._headers(),
            )
            if response.status_code == 200:
                payload = response.json()
                self._remaining_wu = int(payload.get("balance_wu", 0))
        except Exception as exc:
            logger.warning("Failed to refresh WU balance from control plane: %s", exc)

    def _refresh_balance_sync(self) -> None:
        _run_async(self._refresh_balance_async())

    def check_budget(self, cost: float) -> BudgetStatus:
        if not self._configured:
            return BudgetStatus.EXCEEDED

        if cost <= 0:
            self._refresh_balance_sync()
            if self._remaining_wu <= 0:
                return BudgetStatus.EXCEEDED
            return BudgetStatus.OK

        amount_wu = self._usd_to_wu(cost)
        if self._remaining_wu < amount_wu:
            self._emit_exceeded(float(amount_wu), float(max(self._remaining_wu, 0)))
            return BudgetStatus.EXCEEDED

        try:
            status = _run_async(self._reserve_async(amount_wu))
            return status
        except Exception as exc:
            logger.error("WU reserve failed: %s", exc)
            return BudgetStatus.EXCEEDED

    async def _reserve_async(self, amount_wu: int) -> BudgetStatus:
        client = self._get_client()
        response = await client.post(
            f"{self._base_url}/api/internal/billing/reserve",
            headers=self._headers(),
            json={"amount_wu": amount_wu, "category": "llm_output"},
        )
        if response.status_code == 402:
            await self._refresh_balance_async()
            self._emit_exceeded(float(amount_wu), float(self._remaining_wu))
            return BudgetStatus.EXCEEDED
        response.raise_for_status()
        payload = response.json()
        self._active_reservation_id = str(payload["reservation_id"])
        self._reserved_wu = amount_wu
        self._remaining_wu = max(0, self._remaining_wu - amount_wu)

        warning_threshold = 0.2
        if self._remaining_wu <= int(self._reserved_wu * warning_threshold):
            return BudgetStatus.WARNING
        return BudgetStatus.OK

    def record_cost(self, cost: float) -> BudgetStatus:
        if not self._configured or self._active_reservation_id is None:
            return BudgetStatus.OK

        actual_wu = self._usd_to_wu(cost)
        try:
            return _run_async(self._commit_async(actual_wu))
        except Exception as exc:
            logger.error("WU commit failed: %s", exc)
            return BudgetStatus.EXCEEDED

    async def _commit_async(self, actual_wu: int) -> BudgetStatus:
        reservation_id = self._active_reservation_id
        if reservation_id is None:
            return BudgetStatus.OK

        client = self._get_client()
        try:
            response = await client.post(
                f"{self._base_url}/api/internal/billing/commit",
                headers=self._headers(),
                json={"reservation_id": reservation_id, "actual_wu": actual_wu},
            )
            response.raise_for_status()
        except Exception:
            try:
                await client.post(
                    f"{self._base_url}/api/internal/billing/release",
                    headers=self._headers(),
                    json={"reservation_id": reservation_id},
                )
            except Exception as release_exc:
                logger.error("WU release after commit failure also failed: %s", release_exc)
            raise
        finally:
            self._active_reservation_id = None
            self._reserved_wu = 0
            await self._refresh_balance_async()

        if self._remaining_wu <= 0:
            return BudgetStatus.EXCEEDED
        if self._remaining_wu < 50:
            return BudgetStatus.WARNING
        return BudgetStatus.OK

    def get_remaining_budget(self) -> float | None:
        if not self._configured:
            return 0.0
        return float(self._remaining_wu)

    def _emit_exceeded(self, required_wu: float, available_wu: float) -> None:
        try:
            from app.services.event.app_event_bus import AppEvent, AppEventType, get_event_bus

            limit = max(available_wu, required_wu)
            pct = round((required_wu / limit) * 100, 1) if limit > 0 else 100.0
            get_event_bus().publish(
                AppEvent(
                    event_type=AppEventType.BUDGET_ALERT,
                    data={
                        "subtype": "budget_alert",
                        "status": "exceeded",
                        "dimension": "work_units",
                        "today_cost": round(required_wu, 6),
                        "daily_limit": round(limit, 6),
                        "remaining": 0.0,
                        "pct": pct,
                        "eco_mode": True,
                    },
                )
            )
        except Exception as exc:
            logger.warning("Failed to emit WU exceeded SSE: %s", exc)
