"""健康检查端点

提供多层级健康检查接口，用于：
- 容器编排（K8s liveness/readiness probe）
- 运维监控（Prometheus、Grafana）
- 系统诊断和调试

端点：
- GET /api/v1/health - 基础健康检查（liveness）
- GET /api/v1/health/ready - 就绪检查（readiness），检查所有依赖服务
- GET /api/v1/health/info - 系统配置信息（部署模式、数据库类型等）
- GET /api/v1/health/browser - 浏览器运行时健康状态
- GET /api/v1/health/browser/doctor - 完整浏览器诊断
- GET /api/v1/health/browser/orphans - 列出孤儿自动化进程
- DELETE /api/v1/health/browser/orphans - 清理孤儿进程（需要 confirm 参数）
- POST /api/v1/health/browser/test-cloud-connection - 测试云浏览器连接
"""

import logging

from fastapi import APIRouter, HTTPException, Query
from myrm_agent_harness.observability.diagnostics.manager import run_all_diagnostics
from sqlalchemy import text
from sqlalchemy.exc import OperationalError as SQLAlchemyOperationalError

from app.api.health.benchmark import router as benchmark_router
from app.api.health.diagnostic import router as diagnostic_router
from app.api.health.memory import router as memory_router
from app.database.connection import get_session
from app.services.event.app_event_bus import AppEvent, AppEventType, get_event_bus
from app.services.repair import (
    RepairActionExecuteRequest,
    RepairActionExecuteResult,
    execute_repair_action,
)
from app.services.repair.actions import RepairActionId, build_repair_actions

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])
router.include_router(benchmark_router)
router.include_router(diagnostic_router)
router.include_router(memory_router)


@router.get("")
async def health_check() -> dict[str, object]:
    """健康检查端点

    基础健康检查，只检查服务是否运行。

    Returns:
        dict: 包含状态信息和功能特性的字典
    """
    from app.server.runtime_dev_info import get_runtime_dev_info
    from app.server.status import system_status

    dev = get_runtime_dev_info()
    return {
        "status": "healthy",
        "message": "MyrmAgent backend is running",
        "dev_mode": dev["dev_mode"],
        "listen_port": dev["listen_port"],
        "listen_host": dev["listen_host"],
        "frontend_proxy_port": dev["frontend_proxy_port"],
        "features": {
            "websocket_enabled": True,
        },
        "system_status": {
            "database_recovered": system_status.database_recovered,
            "database_degraded": system_status.database_degraded,
        },
    }


@router.get("/ready")
async def readiness_check() -> dict[str, bool | dict[str, bool]]:
    """就绪检查端点

    检查所有依赖服务是否就绪（数据库、向量库、图数据库等）

    Returns:
        dict: 包含就绪状态的字典
    """
    checks: dict[str, bool] = {}

    # 检查数据库连接
    try:
        async with get_session() as session:
            await session.execute(text("SELECT 1"))
        checks["database"] = True
    except Exception as e:
        logger.warning("Database check failed: %s", e)
        checks["database"] = False

    # 检查 Qdrant 连接
    try:
        from app.core.retriever.vector.defaults import create_default_vector_store

        _ = await create_default_vector_store()
        checks["qdrant"] = True
    except Exception as e:
        logger.warning("Qdrant check failed: %s", e)
        checks["qdrant"] = False

    # 检查图数据库连接
    try:
        from app.core.retriever import get_graph_store

        graph_store = get_graph_store(memory_enabled=True)

        if graph_store:
            # 异步健康检查
            is_healthy = await graph_store.health_check()
            checks["graph_db"] = is_healthy
        else:
            # 未启用图功能
            checks["graph_db"] = True  # 不影响就绪状态
    except Exception as e:
        logger.warning("Graph database check failed: %s", e)
        checks["graph_db"] = False

    # 所有检查都通过才算就绪
    all_ready = all(checks.values())

    return {
        "ready": all_ready,
        "checks": checks,
    }


def _check_local_stt_installed() -> bool:
    """Check if faster-whisper STT dependencies are importable."""
    try:
        import faster_whisper  # noqa: F401

        return True
    except ImportError:
        return False


def _get_tokenizer_backend() -> str:
    """Return the active tokenizer backend name (jieba or bigram_fallback)."""
    try:
        from myrm_agent_harness.toolkits.retriever.bm25 import get_tokenizer_service

        return get_tokenizer_service().backend
    except Exception:
        return "unavailable"


@router.get("/info")
async def system_info() -> dict[str, object]:
    """系统信息端点

    返回当前部署模式和配置信息，用于：
    - 运维诊断和调试
    - 监控面板显示系统配置
    - CI/CD 流程验证部署配置

    注意：前端不再使用此端点检测部署模式，改用环境变量配置

    Returns:
        dict: 系统配置信息
            - deploy_mode: 部署模式（local/sandbox）
            - database: 数据库类型（sqlite）
            - qdrant: 向量数据库模式（embedded）
            - embedding: 嵌入模型服务（builtin/custom/cloud）
            - reranker: 重排序模型服务（builtin/custom/cloud）
            - local_stt_available: 本地语音识别组件是否就绪
    """
    from app.config.deploy_mode import (
        get_database_mode,
        get_deploy_mode,
        get_embedding_mode,
        get_qdrant_mode,
        get_reranker_mode,
    )

    return {
        "deploy_mode": get_deploy_mode().value,
        "database": get_database_mode().value,
        "qdrant": get_qdrant_mode().value,
        "embedding": get_embedding_mode().value,
        "reranker": get_reranker_mode().value,
        "local_stt_available": _check_local_stt_installed(),
        "tokenizer_backend": _get_tokenizer_backend(),
    }


@router.get("/metrics")
async def system_metrics() -> dict[str, object]:
    """获取系统级监控指标

    暴露给 Control Plane 用于沙箱健康度监控。需要管理员权限。
    包括：
    - DLQ (死信队列) 堆积量
    - memory_pressure: 内存压力等级和使用率
    - 数据库连接池状态 (可选)
    """
    from app.core.channel_bridge import get_channel_gateway
    from app.lifecycle.monitors import get_memory_pressure_monitor_instance

    dlq_metrics: dict[str, object] = {"failed_count": 0, "status": "healthy"}

    try:
        gateway = get_channel_gateway()
        if gateway and gateway.bus and gateway.bus._dlq:
            failed_count = await gateway.bus._dlq.get_failed_count()
            dlq_metrics["failed_count"] = failed_count
            if failed_count > 500:
                dlq_metrics["status"] = "unhealthy"
            elif failed_count > 100:
                dlq_metrics["status"] = "degraded"
    except Exception as e:
        dlq_metrics["error"] = str(e)
        dlq_metrics["status"] = "unknown"

    memory_metrics: dict[str, object] = {"level": "unknown", "percent": 0.0}
    monitor = get_memory_pressure_monitor_instance()
    if monitor is not None:
        memory_metrics = {
            "level": monitor.current_level.name,
            "percent": round(monitor.current_memory_percent, 1),
        }

    return {"dlq": dlq_metrics, "memory_pressure": memory_metrics}


@router.get("/memory/search")
async def memory_search_diagnostics() -> dict[str, object]:
    """Memory search quality diagnostics.

    Returns a snapshot of retrieval metrics: zero-result rate, score
    distribution, latency percentiles, and per-type hit rates.
    """
    from myrm_agent_harness.toolkits.memory.metrics import get_search_metrics

    snapshot = get_search_metrics().snapshot()
    return {
        "total_searches": snapshot.total_searches,
        "zero_result_count": snapshot.zero_result_count,
        "zero_result_rate": snapshot.zero_result_rate,
        "avg_score": snapshot.avg_score,
        "min_score": snapshot.min_score,
        "max_score": snapshot.max_score,
        "avg_result_count": snapshot.avg_result_count,
        "avg_latency_ms": snapshot.avg_latency_ms,
        "p95_latency_ms": snapshot.p95_latency_ms,
        "hit_rate_by_type": snapshot.hit_rate_by_type,
    }


@router.get("/browser")
async def browser_health() -> dict[str, object]:
    """Browser runtime health check.

    Returns:
        Health status with "healthy" | "degraded" | "unhealthy"
    """
    from myrm_agent_harness.toolkits.browser.pool import get_global_browser_pool

    try:
        pool = get_global_browser_pool()
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

    report = await run_doctor(include_launch_test=launch_test)

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
    from myrm_agent_harness.toolkits.browser import find_orphan_chromium_processes

    orphans = find_orphan_chromium_processes()

    return {
        "count": len(orphans),
        "orphans": orphans,
        "message": (f"Found {len(orphans)} orphan automation process(es)" if orphans else "No orphan processes found"),
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
        find_orphan_chromium_processes,
    )

    try:
        orphans = find_orphan_chromium_processes()

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
        raise HTTPException(status_code=500, detail=f"Failed to process orphans: {exc}") from exc


@router.post("/browser/test-cloud-connection")
async def test_cloud_browser_connection() -> dict[str, object]:
    """Test connectivity to the configured cloud browser provider.

    Reads the current browserCloudProvider config, resolves the WS endpoint,
    and attempts a WebSocket handshake to verify connectivity.

    Returns:
        Connection test result with status, latency, and provider info
    """
    import asyncio
    import time as _time

    from app.schemas.config import BrowserCloudProviderConfigValue
    from app.services.config.service import config_service

    record = await config_service.get("browserCloudProvider")
    if not record:
        return {"status": "not_configured", "message": "No cloud browser provider configured"}

    config = BrowserCloudProviderConfigValue.model_validate(record.value)
    if not config.enabled:
        return {"status": "disabled", "message": "Cloud browser provider is disabled"}

    endpoint = config.resolve_ws_endpoint()
    if not endpoint:
        return {"status": "invalid", "message": "Cannot resolve WebSocket endpoint (missing credential?)"}

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
            return {"status": "error", "message": "No WebSocket library available (install websockets or aiohttp)"}
        except Exception as exc:
            return {"status": "failed", "provider": config.provider, "error": str(exc)}
    except Exception as exc:
        return {"status": "failed", "provider": config.provider, "error": str(exc)}


@router.get("/doctor")
async def system_doctor() -> dict[str, object]:
    """
    聚合底层 Harness 框架与 Server 业务层的健康检查报告，
    返回给前端的“系统状态大屏”呈现。
    """
    from myrm_agent_harness.agent.middlewares._session_context import (
        get_terminal_errors,
    )
    from myrm_agent_harness.observability.diagnostics.protocols import HealthReport, redact_health_report

    # 1. 获取底座 Harness 框架的健康度 (解耦调用)
    harness_reports = await run_all_diagnostics()

    # 1.5 捕获底层安全/终端错误 (Terminal Errors)
    registry = get_terminal_errors()
    registry._load()
    errors = list(registry.get_all())
    if errors:
        harness_reports.append(
            HealthReport(
                component_name="AgentEngine",
                status="fail",
                message="Agent engine has encountered a critical error.",
                detail=f"Terminal error detected: {'; '.join(errors)}",
                fix_suggestion="Try restarting the application.",
            )
        )
    elif not any(r.component_name == "AgentEngine" for r in harness_reports):
        harness_reports.append(
            HealthReport(
                component_name="AgentEngine",
                status="pass",
                message="Agent engine is running normally.",
            )
        )

    # 2. 获取 Server 自身的健康度 (全链路依赖探测)
    from app.core.infra.health.server_diagnostics import run_server_diagnostics

    server_reports = list(await run_server_diagnostics())

    # 将状态通过 SSE 广播（脱敏后）
    for report in server_reports:
        if report.status in ("fail", "warn"):
            redacted = redact_health_report(report)
            get_event_bus().publish(
                AppEvent(
                    event_type=AppEventType.HEALTH_ALERT,
                    data={
                        "component": redacted.component_name,
                        "status": redacted.status,
                        "code": redacted.code,
                        "message": redacted.message,
                        "detail": redacted.detail,
                        "fix_suggestion": redacted.fix_suggestion,
                        "layer": "server",
                    },
                )
            )

    # 3. 生成结构化修复建议。执行仍由白名单 repair endpoint 控制。
    repair_actions = await build_repair_actions(harness_reports, server_reports)

    # 4. 发布fail/warn事件用于SSE告警（脱敏后）
    for report in harness_reports:
        if report.status in ("fail", "warn"):
            redacted = redact_health_report(report)
            get_event_bus().publish(
                AppEvent(
                    event_type=AppEventType.HEALTH_ALERT,
                    data={
                        "component": redacted.component_name,
                        "status": redacted.status,
                        "code": redacted.code,
                        "message": redacted.message,
                        "detail": redacted.detail,
                        "fix_suggestion": redacted.fix_suggestion,
                        "layer": "harness",
                    },
                )
            )

    harness_payload: list[object] = [
        redact_health_report(report).model_dump() if hasattr(report, "model_dump") else report for report in harness_reports
    ]
    server_payload: list[object] = [
        redact_health_report(report).model_dump() if hasattr(report, "model_dump") else report for report in server_reports
    ]
    return {
        "server": server_payload,
        "harness": harness_payload,
        "repair_actions": [action.model_dump(mode="json") for action in repair_actions],
    }


@router.post("/repair-actions/{action_id}/execute", response_model=RepairActionExecuteResult)
async def execute_health_repair_action(
    action_id: RepairActionId,
    request: RepairActionExecuteRequest,
) -> RepairActionExecuteResult:
    """Execute a white-listed runtime repair action.

    The endpoint intentionally accepts only known enum action IDs and delegates
    execution to the repair service. Agents and clients cannot submit arbitrary
    SQL, shell commands, or file paths.
    """

    return await execute_repair_action(action_id, request)


@router.post("/database/reset")
async def reset_database() -> dict[str, str]:
    """重置数据库端点

    用于在数据库严重损坏且降级到内存模式后，用户主动请求重置数据库。
    将删除现有的数据库文件及 WAL 文件，并重新初始化。
    """
    from pathlib import Path

    from app.config.settings import settings
    from app.database.connection import init_database
    from app.database.recovery import _cleanup_wal_files
    from app.platform_utils import reset_database_engine
    from app.server.status import system_status

    try:
        # 1. 释放当前所有数据库连接
        await reset_database_engine()

        # 2. 删除物理文件
        db_path = Path(settings.database.sqlite_path)
        if db_path.exists():
            db_path.unlink()
        _cleanup_wal_files(db_path)

        # 3. 重新初始化数据库
        await init_database()

        # 4. 恢复系统状态
        system_status.database_degraded = False
        system_status.database_recovered = False

        return {"status": "success", "message": "Database has been reset successfully."}
    except Exception as e:
        logger.error("Failed to reset database: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to reset database: {e}") from e


@router.get("/history")
async def health_history(hours: int = 24) -> dict[str, object]:
    """获取系统健康历史数据 (用于趋势图)

    Args:
        hours: 查询最近N小时的数据 (默认24小时)

    Returns:
        List of health history records with timestamp, status, score
    """
    from datetime import datetime, timedelta
    from datetime import timezone as tz

    if hours < 1 or hours > 168:
        raise HTTPException(status_code=400, detail="Hours parameter must be between 1 and 168 (7 days)")

    cutoff_time = (datetime.now(tz.utc) - timedelta(hours=hours)).isoformat()

    try:
        async with get_session() as session:
            result = await session.execute(
                text(
                    """SELECT timestamp, overall_status, overall_score, component_reports
                       FROM system_health_history
                       WHERE timestamp >= :cutoff
                       ORDER BY timestamp ASC"""
                ),
                {"cutoff": cutoff_time},
            )
            rows = result.fetchall()
    except SQLAlchemyOperationalError as exc:
        err = str(exc).lower()
        if "no such table" in err or "does not exist" in err:
            logger.warning("system_health_history not available yet: %s", exc)
            rows = []
        else:
            raise

    return {
        "data": [
            {
                "timestamp": (row[0] if isinstance(row[0], str) else (row[0].isoformat() if row[0] else None)),
                "status": row[1],
                "score": row[2],
                "components": row[3] if len(row) > 3 else None,
            }
            for row in rows
        ]
    }


@router.get("/resources")
async def resource_health_check(
    auto_recover: bool = Query(False, description="Automatically recover unhealthy resources"),
    force_recovery: bool = Query(False, description="Allow dangerous recovery actions (SQLite WAL deletion)"),
) -> dict[str, object]:
    """Resource-level health check (Qdrant, SQLite, Browser).

    Checks and optionally recovers unhealthy resources.
    Safe by default: only attempts recovery if auto_recover=true.

    Args:
        auto_recover: Enable automatic recovery on failure
        force_recovery: Allow dangerous recovery actions (SQLite WAL deletion)

    Returns:
        Resource health status and recovery results
    """
    from app.core.infra.health import run_all_health_checks

    try:
        all_healthy, results = await run_all_health_checks(
            auto_recover=auto_recover,
            force_sqlite_wal_cleanup=force_recovery,
            max_retries=1,
        )

        formatted_results = []
        for name, check_result, recovery_result in results:
            item: dict[str, object] = {
                "name": name,
                "status": check_result.status.value if check_result else "unknown",
                "message": check_result.message if check_result else "No check result",
                "details": check_result.details if check_result else None,
                "checked_at": (check_result.checked_at.isoformat() if check_result and check_result.checked_at else None),
            }

            if recovery_result:
                item["recovery"] = {
                    "status": recovery_result.status.value,
                    "message": recovery_result.message,
                    "actions_taken": recovery_result.actions_taken,
                    "details": recovery_result.details,
                    "recovered_at": (recovery_result.recovered_at.isoformat() if recovery_result.recovered_at else None),
                }

            formatted_results.append(item)

        return {
            "all_healthy": all_healthy,
            "auto_recover": auto_recover,
            "force_recovery": force_recovery,
            "resources": formatted_results,
        }

    except Exception as exc:
        logger.error("Resource health check failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Resource health check failed: {exc}") from exc
