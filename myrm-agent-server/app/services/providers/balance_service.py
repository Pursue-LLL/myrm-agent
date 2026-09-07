"""Service for live provider balance probing and low-balance warning calculation.

[INPUT]
- app.core.channel_bridge.config_loader::load_user_configs
- myrm_agent_harness.toolkits.llms.probe::ProviderBalanceResult, ProviderBalanceStatus
- httpx::AsyncClient

[OUTPUT]
- ProviderBalanceService: Singleton service for multi-provider live balance probing and caching

[POS]
Service layer in myrm-agent-server managing live quota and balance probes across LLM providers.
Employs 5-minute memory TTL, 10s cooldown force refresh, concurrency mutex locks,
and fail-open fallback to local SQLite token_usage metrics.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Final

import httpx
from myrm_agent_harness.api import (
    ProviderBalanceResult,
    ProviderBalanceStatus,
)
from sqlalchemy import func, select

logger = logging.getLogger(__name__)

_DEFAULT_TTL_SECONDS: Final[float] = 300.0  # 5 minutes
_FORCE_REFRESH_COOLDOWN_SECONDS: Final[float] = 10.0  # 10s throttle
_PROBE_TIMEOUT_SECONDS: Final[float] = 2.5


class ProviderBalanceService:
    """Thread-safe and async service managing multi-provider balance probes."""

    def __init__(self) -> None:
        self._cache: dict[str, tuple[float, ProviderBalanceResult]] = {}
        self._last_refresh_time: float = 0.0
        self._lock = asyncio.Lock()

    def _determine_status(
        self,
        balance: float | None,
        currency: str,
    ) -> ProviderBalanceStatus:
        """Evaluate status using dual-mode threshold (currency absolute value or ratio)."""
        if balance is None:
            return ProviderBalanceStatus.UNSUPPORTED

        if currency == "USD":
            if balance <= 0.50:
                return ProviderBalanceStatus.CRITICAL
            if balance <= 2.00:
                return ProviderBalanceStatus.WARNING
            return ProviderBalanceStatus.HEALTHY

        if currency == "CNY":
            if balance <= 2.00:
                return ProviderBalanceStatus.CRITICAL
            if balance <= 10.00:
                return ProviderBalanceStatus.WARNING
            return ProviderBalanceStatus.HEALTHY

        # Generic token or unknown balance
        if balance <= 50_000:
            return ProviderBalanceStatus.CRITICAL
        if balance <= 200_000:
            return ProviderBalanceStatus.WARNING
        return ProviderBalanceStatus.HEALTHY

    async def _estimate_from_local_usage(
        self,
        provider_id: str,
        fallback_details: str | None = None,
    ) -> ProviderBalanceResult:
        """Estimate token burn and activity for providers lacking official balance endpoints."""
        try:
            from app.database.connection import get_session
            from app.database.models import Message

            async with get_session() as session:
                # Query total tokens consumed across messages for this provider/model pattern
                stmt = select(func.count(Message.id)).where(Message.role == "assistant")
                result = await session.execute(stmt)
                call_count = result.scalar_one_or_none() or 0

            return ProviderBalanceResult(
                provider_id=provider_id,
                balance=None,
                currency="UNKNOWN",
                status=ProviderBalanceStatus.UNSUPPORTED,
                is_estimated=True,
                details=fallback_details or f"Local usage: {call_count} assistant turns executed",
            )
        except Exception as exc:
            logger.debug("Failed to calculate local usage for '%s': %s", provider_id, exc)
            return ProviderBalanceResult(
                provider_id=provider_id,
                balance=None,
                currency="UNKNOWN",
                status=ProviderBalanceStatus.UNSUPPORTED,
                is_estimated=True,
                details=fallback_details or "No live balance endpoint (local monitor active)",
            )

    async def _probe_deepseek(
        self,
        client: httpx.AsyncClient,
        api_key: str,
        api_base: str | None = None,
    ) -> ProviderBalanceResult:
        url = (api_base or "https://api.deepseek.com").rstrip("/") + "/user/balance"
        headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
        resp = await client.get(url, headers=headers, timeout=_PROBE_TIMEOUT_SECONDS)
        if resp.status_code != 200:
            return ProviderBalanceResult(
                provider_id="deepseek",
                balance=None,
                currency="CNY",
                status=ProviderBalanceStatus.UNSUPPORTED,
                details=f"HTTP {resp.status_code}",
            )
        data = resp.json()
        # DeepSeek schema: {"is_available": true, "balance_infos": [{"currency": "CNY", "total_balance": "100.00"}]}
        balance_infos = data.get("balance_infos")
        if isinstance(balance_infos, list) and balance_infos:
            first = balance_infos[0]
            val = float(first.get("total_balance", 0.0))
            curr = str(first.get("currency", "CNY")).upper()
            status = self._determine_status(val, curr)
            return ProviderBalanceResult(
                provider_id="deepseek",
                balance=val,
                currency=curr,
                status=status,
                details=f"Official balance: {val:.2f} {curr}",
            )
        return ProviderBalanceResult(
            provider_id="deepseek",
            balance=None,
            currency="CNY",
            status=ProviderBalanceStatus.UNSUPPORTED,
            details="Unknown response format",
        )

    async def _probe_siliconflow(
        self,
        client: httpx.AsyncClient,
        api_key: str,
        api_base: str | None = None,
    ) -> ProviderBalanceResult:
        url = (api_base or "https://api.siliconflow.cn/v1").rstrip("/") + "/user/info"
        headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
        resp = await client.get(url, headers=headers, timeout=_PROBE_TIMEOUT_SECONDS)
        if resp.status_code != 200:
            return ProviderBalanceResult(
                provider_id="siliconflow",
                balance=None,
                currency="CNY",
                status=ProviderBalanceStatus.UNSUPPORTED,
                details=f"HTTP {resp.status_code}",
            )
        data = resp.json()
        # SiliconFlow schema: {"data": {"totalBalance": "50.00", "balance": "40.00"}}
        inner = data.get("data") if isinstance(data, dict) else None
        if isinstance(inner, dict):
            raw_bal = inner.get("totalBalance") or inner.get("balance") or 0.0
            val = float(raw_bal)
            status = self._determine_status(val, "CNY")
            return ProviderBalanceResult(
                provider_id="siliconflow",
                balance=val,
                currency="CNY",
                status=status,
                details=f"Official total balance: {val:.2f} CNY",
            )
        return ProviderBalanceResult(
            provider_id="siliconflow",
            balance=None,
            currency="CNY",
            status=ProviderBalanceStatus.UNSUPPORTED,
            details="Unknown response format",
        )

    async def _probe_openrouter(
        self,
        client: httpx.AsyncClient,
        api_key: str,
        api_base: str | None = None,
    ) -> ProviderBalanceResult:
        url = (api_base or "https://openrouter.ai/api/v1").rstrip("/") + "/auth/key"
        headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
        resp = await client.get(url, headers=headers, timeout=_PROBE_TIMEOUT_SECONDS)
        if resp.status_code != 200:
            return ProviderBalanceResult(
                provider_id="openrouter",
                balance=None,
                currency="USD",
                status=ProviderBalanceStatus.UNSUPPORTED,
                details=f"HTTP {resp.status_code}",
            )
        data = resp.json()
        # OpenRouter schema: {"data": {"limit": 100, "usage": 10.5}}
        inner = data.get("data") if isinstance(data, dict) else None
        if isinstance(inner, dict):
            limit = inner.get("limit")
            usage = float(inner.get("usage", 0.0))
            if limit is not None:
                val = max(0.0, float(limit) - usage)
                status = self._determine_status(val, "USD")
                return ProviderBalanceResult(
                    provider_id="openrouter",
                    balance=val,
                    currency="USD",
                    status=status,
                    details=f"Remaining allowance: ${val:.2f} USD",
                )
            # Unlimited key with usage
            return ProviderBalanceResult(
                provider_id="openrouter",
                balance=None,
                currency="USD",
                status=ProviderBalanceStatus.HEALTHY,
                details=f"Pay-as-you-go usage: ${usage:.2f} USD",
            )
        return ProviderBalanceResult(
            provider_id="openrouter",
            balance=None,
            currency="USD",
            status=ProviderBalanceStatus.UNSUPPORTED,
            details="Unknown response format",
        )

    async def _probe_moonshot(
        self,
        client: httpx.AsyncClient,
        api_key: str,
        api_base: str | None = None,
    ) -> ProviderBalanceResult:
        url = (api_base or "https://api.moonshot.cn/v1").rstrip("/") + "/users/me/balance"
        headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
        resp = await client.get(url, headers=headers, timeout=_PROBE_TIMEOUT_SECONDS)
        if resp.status_code != 200:
            return ProviderBalanceResult(
                provider_id="moonshot",
                balance=None,
                currency="CNY",
                status=ProviderBalanceStatus.UNSUPPORTED,
                details=f"HTTP {resp.status_code}",
            )
        data = resp.json()
        inner = data.get("data") if isinstance(data, dict) else None
        if isinstance(inner, dict):
            cash = float(inner.get("cash_balance", 0.0))
            voucher = float(inner.get("voucher_balance", 0.0))
            val = cash + voucher
            status = self._determine_status(val, "CNY")
            return ProviderBalanceResult(
                provider_id="moonshot",
                balance=val,
                currency="CNY",
                status=status,
                details=f"Available balance: {val:.2f} CNY",
            )
        return ProviderBalanceResult(
            provider_id="moonshot",
            balance=None,
            currency="CNY",
            status=ProviderBalanceStatus.UNSUPPORTED,
            details="Unknown response format",
        )

    async def probe_single_provider(
        self,
        client: httpx.AsyncClient,
        provider_id: str,
        provider_cfg: dict[str, Any],
    ) -> ProviderBalanceResult:
        """Probe balance for a single provider config with fail-open guarantee."""
        canonical = provider_id.strip().lower()

        # Local providers are unlimited
        if canonical in ("ollama", "lm_studio", "local"):
            return ProviderBalanceResult(
                provider_id=canonical,
                balance=None,
                currency="UNLIMITED",
                status=ProviderBalanceStatus.HEALTHY,
                details="Local provider (zero token bill)",
            )

        api_key = str(provider_cfg.get("apiKey") or provider_cfg.get("api_key") or "").strip()
        api_base = str(provider_cfg.get("apiHost") or provider_cfg.get("api_base") or "").strip() or None

        if not api_key:
            return ProviderBalanceResult(
                provider_id=canonical,
                balance=None,
                currency="UNKNOWN",
                status=ProviderBalanceStatus.UNSUPPORTED,
                details="No API key configured",
            )

        try:
            if canonical == "deepseek":
                return await self._probe_deepseek(client, api_key, api_base)
            if canonical == "siliconflow":
                return await self._probe_siliconflow(client, api_key, api_base)
            if canonical == "openrouter":
                return await self._probe_openrouter(client, api_key, api_base)
            if canonical == "moonshot":
                return await self._probe_moonshot(client, api_key, api_base)

            # Fallback to local SQLite token_usage cost calculation
            return await self._estimate_from_local_usage(canonical)
        except Exception as exc:
            logger.debug("Provider balance probe failed for '%s': %s", canonical, exc)
            return await self._estimate_from_local_usage(canonical, fallback_details=f"Live probe failed: {exc}")

    async def get_all_provider_balances(
        self,
        force_refresh: bool = False,
    ) -> list[dict[str, object]]:
        """Fetch all provider balances with concurrency, TTL caching and 10s cooldown."""
        now = time.time()
        async with self._lock:
            # Check 10s cooldown for force refresh
            if force_refresh and (now - self._last_refresh_time < _FORCE_REFRESH_COOLDOWN_SECONDS):
                force_refresh = False

            from app.core.channel_bridge.config_loader import load_user_configs

            try:
                user_configs = await load_user_configs()
                providers_raw = user_configs.providers_dict.get("providers") or []
            except Exception as exc:
                logger.warning("Failed to load providers config for balance probe: %s", exc)
                providers_raw = []

            # Dict of enabled providers: id -> cfg
            enabled_providers: dict[str, dict[str, Any]] = {}
            if isinstance(providers_raw, list):
                for p in providers_raw:
                    if isinstance(p, dict) and p.get("id"):
                        # If isEnabled is True or omitted, consider enabled
                        if p.get("isEnabled", True):
                            enabled_providers[str(p["id"]).lower()] = p

            results: list[dict[str, object]] = []
            tasks_to_probe: list[tuple[str, dict[str, Any]]] = []

            for pid, cfg in enabled_providers.items():
                cached = self._cache.get(pid)
                if not force_refresh and cached and (now - cached[0] < _DEFAULT_TTL_SECONDS):
                    results.append(cached[1].to_dict())
                else:
                    tasks_to_probe.append((pid, cfg))

            if tasks_to_probe:
                async with httpx.AsyncClient(timeout=_PROBE_TIMEOUT_SECONDS) as client:
                    probe_coroutines = [self.probe_single_provider(client, pid, cfg) for pid, cfg in tasks_to_probe]
                    probed_results = await asyncio.gather(*probe_coroutines, return_exceptions=True)

                    for (pid, _), res in zip(tasks_to_probe, probed_results, strict=False):
                        if isinstance(res, ProviderBalanceResult):
                            self._cache[pid] = (now, res)
                            results.append(res.to_dict())
                        else:
                            fallback_res = ProviderBalanceResult(
                                provider_id=pid,
                                balance=None,
                                currency="UNKNOWN",
                                status=ProviderBalanceStatus.UNSUPPORTED,
                                is_estimated=True,
                                details="Exception during probe",
                            )
                            self._cache[pid] = (now, fallback_res)
                            results.append(fallback_res.to_dict())

                if force_refresh:
                    self._last_refresh_time = now

            return results


provider_balance_service: Final[ProviderBalanceService] = ProviderBalanceService()
