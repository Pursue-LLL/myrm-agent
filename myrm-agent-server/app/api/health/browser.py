"""浏览器运行时健康端点

提供浏览器运行时健康、诊断、孤儿进程管理、云/代理连通性测试。

端点：
- GET /api/v1/health/browser - 浏览器运行时健康状态
- GET /api/v1/health/browser/doctor - 完整浏览器诊断
- GET /api/v1/health/browser/orphans - 列出孤儿自动化进程
- DELETE /api/v1/health/browser/orphans - 清理孤儿进程（需要 confirm 参数）
- POST /api/v1/health/browser/test-cloud-connection - 测试云浏览器连接
- POST /api/v1/health/browser/test-proxy-connection - 测试浏览器代理连接

[INPUT]
- app.config.browser::get_configured_browser_pool (POS: 浏览器池配置)
- myrm_agent_harness.toolkits.browser::run_doctor (POS: 浏览器诊断)
- app.lifecycle.browser::resolve_browser_proxy_pool (POS: 代理池解析)

[OUTPUT]
- browser_health / browser_doctor / 孤儿进程管理 / 连通性测试端点

[POS]
Server business layer. 浏览器运行时健康检查与诊断的 HTTP 端点集合。
"""

import asyncio

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(tags=["health"])


@router.get("/browser")
async def browser_health() -> dict[str, object]:
    """Browser runtime health check.

    Returns:
        Health status with "healthy" | "degraded" | "unhealthy"
    """
    from app.config.browser import get_configured_browser_pool

    try:
        pool = get_configured_browser_pool()
        health_status = await pool.health()
        if isinstance(health_status, dict):
            return {str(k): v for k, v in health_status.items()}
        return {"status": str(health_status)}
    except Exception as exc:
        return {
            "status": "unhealthy",
            "error": str(exc),
            "message": "Failed to get browser pool health",
        }


@router.get("/browser/doctor")
async def browser_doctor(
    launch_test: bool = Query(True, description="Run browser launch test"),
) -> dict[str, object]:
    """Complete browser diagnostics.

    Args:
        launch_test: Whether to test actual browser launch

    Returns:
        Complete diagnostic report with fix suggestions
    """
    from myrm_agent_harness.toolkits.browser import run_doctor

    from app.config.settings import settings
    from app.lifecycle.browser import resolve_browser_proxy_pool

    proxy_pool = await resolve_browser_proxy_pool()
    browser_proxy = ",".join(proxy_pool.urls) if proxy_pool else ""

    report = await run_doctor(
        include_launch_test=launch_test,
        browser_proxy=browser_proxy,
        extension_relay_base_url=f"http://127.0.0.1:{settings.port}",
    )

    return {
        "summary": report.summary,
        "overall_healthy": report.overall_healthy,
        "checks": {
            name: {
                "status": check.status.value,
                "message": check.message,
                "fix": check.fix,
                "details": check.details,
            }
            for name, check in report.checks.items()
        },
        "recommendations": report.recommendations,
    }


@router.get("/browser/orphans")
async def list_browser_orphans() -> dict[str, object]:
    """List orphan automation browser processes.

    Returns:
        List of orphan processes with PIDs, names, and user-data-dir paths
    """
    from myrm_agent_harness.toolkits.browser import find_orphan_automation_processes

    orphans = await asyncio.to_thread(find_orphan_automation_processes)

    return {
        "count": len(orphans),
        "orphans": orphans,
        "message": (
            f"Found {len(orphans)} orphan automation process(es)"
            if orphans
            else "No orphan processes found"
        ),
    }


@router.delete("/browser/orphans")
async def cleanup_browser_orphans(
    confirm: bool = Query(False, description="Must be True to actually kill processes"),
) -> dict[str, object]:
    """Clean up orphan automation browser processes.

    Safety mechanism: requires confirm=true to actually kill processes.
    Otherwise returns dry-run results only.

    Args:
        confirm: Must be True to execute cleanup (safety confirmation)

    Returns:
        Cleanup result with dry_run flag, killed count, and failed list
    """
    from myrm_agent_harness.toolkits.browser import (
        cleanup_orphan_processes,
        find_orphan_automation_processes,
    )

    try:
        orphans = await asyncio.to_thread(find_orphan_automation_processes)

        if not orphans:
            return {
                "killed": 0,
                "dry_run": False,
                "message": "No orphan automation processes found",
                "orphans": [],
            }

        orphan_pids = [o["pid"] for o in orphans]
        result = cleanup_orphan_processes(orphan_pids, force=confirm)

        return {
            "killed": result["killed"],
            "dry_run": result["dry_run"],
            "message": result.get("message", f"Killed {result['killed']} process(es)"),
            "orphans": orphans,
            "failed": result.get("failed", []),
        }
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail="Failed to process orphans"
        ) from exc


@router.post("/browser/test-cloud-connection")
async def test_cloud_browser_connection() -> dict[str, object]:
    """Test connectivity to the configured cloud browser provider.

    Reads the current browserCloudProvider config, resolves the WS endpoint,
    and attempts a WebSocket handshake to verify connectivity.

    Returns:
        Connection test result with status, latency, and provider info
    """
    import time as _time

    from app.schemas.config import BrowserCloudProviderConfigValue
    from app.services.config.service import config_service

    record = await config_service.get("browserCloudProvider")
    if not record:
        return {
            "status": "not_configured",
            "message": "No cloud browser provider configured",
        }

    config = BrowserCloudProviderConfigValue.model_validate(record.value)
    if not config.enabled:
        return {"status": "disabled", "message": "Cloud browser provider is disabled"}

    endpoint = config.resolve_ws_endpoint()
    if not endpoint:
        return {
            "status": "invalid",
            "message": "Cannot resolve WebSocket endpoint (missing credential?)",
        }

    try:
        import websockets

        start = _time.perf_counter()
        async with asyncio.timeout(10):
            async with websockets.connect(endpoint, open_timeout=8):
                latency_ms = round((_time.perf_counter() - start) * 1000)
                return {
                    "status": "connected",
                    "provider": config.provider,
                    "latency_ms": latency_ms,
                    "message": f"Successfully connected to {config.provider} ({latency_ms}ms)",
                }
    except ImportError:
        try:
            import aiohttp

            start = _time.perf_counter()
            async with asyncio.timeout(10):
                async with aiohttp.ClientSession() as session:
                    async with session.ws_connect(endpoint, timeout=8):
                        latency_ms = round((_time.perf_counter() - start) * 1000)
                        return {
                            "status": "connected",
                            "provider": config.provider,
                            "latency_ms": latency_ms,
                            "message": f"Successfully connected to {config.provider} ({latency_ms}ms)",
                        }
        except ImportError:
            return {
                "status": "error",
                "message": "No WebSocket library available (install websockets or aiohttp)",
            }
        except Exception as exc:
            return {"status": "failed", "provider": config.provider, "error": str(exc)}
    except Exception as exc:
        return {"status": "failed", "provider": config.provider, "error": str(exc)}


@router.post("/browser/test-proxy-connection")
async def test_browser_proxy_connection() -> dict[str, object]:
    """Test connectivity through the configured browser proxy.

    Reads the current browserProxy config, picks the first proxy URL,
    and attempts an HTTP request through it to verify connectivity.

    Returns:
        Connection test result with status, latency, and proxy count
    """
    import time as _time

    import httpx

    from app.schemas.config import BrowserProxyConfigValue
    from app.services.config.service import config_service

    record = await config_service.get("browserProxy")
    if not record:
        return {"status": "not_configured", "message": "No browser proxy configured"}

    config = BrowserProxyConfigValue.model_validate(record.value)
    if not config.enabled:
        return {"status": "disabled", "message": "Browser proxy is disabled"}

    if not config.proxies:
        return {"status": "invalid", "message": "No proxy URLs configured"}

    proxy_url = config.proxies[0]
    try:
        start = _time.perf_counter()
        async with httpx.AsyncClient(
            proxy=proxy_url,
            timeout=10.0,
            verify=False,  # noqa: S501
        ) as client:
            resp = await client.get("https://httpbin.org/ip")
            latency_ms = round((_time.perf_counter() - start) * 1000)
            if resp.status_code == 200:
                return {
                    "status": "connected",
                    "proxy_count": len(config.proxies),
                    "latency_ms": latency_ms,
                    "egress_ip": resp.json().get("origin", "unknown"),
                    "message": f"Proxy working ({latency_ms}ms, {len(config.proxies)} proxies configured)",
                }
            return {
                "status": "failed",
                "proxy_count": len(config.proxies),
                "error": f"HTTP {resp.status_code}",
            }
    except Exception as exc:
        return {
            "status": "failed",
            "proxy_count": len(config.proxies),
            "error": str(exc),
        }
