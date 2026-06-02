"""Health check business coordinator.

[INPUT]
- myrm_agent_harness.infra.health::run_health_checks (POS: 通用健康检查协调器)
- app.core.infra.health.qdrant::QdrantHealthChecker (POS: Qdrant健康检查器)
- app.core.infra.health.sqlite::SQLiteHealthChecker (POS: SQLite健康检查器)
- app.core.infra.health.browser::BrowserHealthChecker (POS: 浏览器健康检查器)

[OUTPUT]
- run_all_health_checks: 运行所有业务层健康检查

[POS]
业务层健康检查协调器。实例化并运行所有具体的健康检查器。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from myrm_agent_harness.infra.health import run_health_checks

from app.core.infra.health.browser import BrowserHealthChecker
from app.core.infra.health.qdrant import QdrantHealthChecker
from app.core.infra.health.sqlite import SQLiteHealthChecker

if TYPE_CHECKING:
    from myrm_agent_harness.infra.health import HealthCheckResult, RecoveryResult

logger = logging.getLogger(__name__)


async def run_all_health_checks(
    auto_recover: bool = True,
    force_sqlite_wal_cleanup: bool = False,
    max_retries: int = 1,
) -> tuple[bool, list[tuple[str, HealthCheckResult, RecoveryResult | None]]]:
    """Run all business-level health checks.

    Args:
        auto_recover: Whether to automatically attempt recovery on failure
        force_sqlite_wal_cleanup: Whether to allow SQLite WAL file deletion (DANGEROUS)
        max_retries: Maximum number of recovery retries

    Returns:
        Tuple of (all_healthy: bool, results: list of (name, check_result, recovery_result))
    """
    checkers = [
        QdrantHealthChecker(),
        SQLiteHealthChecker(force_wal_cleanup=force_sqlite_wal_cleanup),
        BrowserHealthChecker(),
    ]

    return await run_health_checks(
        checkers=checkers,
        auto_recover=auto_recover,
        max_retries=max_retries,
    )
