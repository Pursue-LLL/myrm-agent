"""
[INPUT] app.api.config.router, app.api.health.router
[OUTPUT] Dev Gate readiness aggregation endpoint (localhost-only)
[POS] 开发门控就绪探针。聚合 provider、edge-tts、config 状态，仅限 localhost 访问。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request

logger = logging.getLogger(__name__)

router = APIRouter(tags=["dev-gate"])

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})


def is_loopback_client(request: Request) -> bool:
    client = request.client
    if client is None:
        return False
    return client.host in _LOOPBACK_HOSTS


@router.get("/readiness")
async def dev_gate_readiness(request: Request) -> dict[str, object]:
    """Aggregate Dev Gate probes for Chrome MCP E2E (localhost only)."""
    if not is_loopback_client(request):
        raise HTTPException(status_code=403, detail="Dev Gate readiness is localhost-only")

    from app.api.config.router import get_config_readiness
    from app.api.health.router import _check_edge_tts_installed, system_info

    config_readiness = await get_config_readiness()
    health_info = await system_info()

    provider = config_readiness.get("provider")
    provider_ready = (
        isinstance(provider, dict) and provider.get("is_ready") is True
    )

    edge_tts_available = _check_edge_tts_installed()
    degraded = config_readiness.get("degraded") is True

    checks: dict[str, bool] = {
        "provider_ready": provider_ready,
        "edge_tts_available": edge_tts_available,
        "config_load_ok": not degraded,
    }
    ready = all(checks.values())

    return {
        "ready": ready,
        "contract_version": "2",
        "checks": checks,
        "provider": provider if isinstance(provider, dict) else {},
        "edge_tts_available": edge_tts_available,
        "deploy_mode": health_info.get("deploy_mode"),
        "degraded": degraded,
    }
