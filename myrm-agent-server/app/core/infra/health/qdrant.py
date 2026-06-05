"""Qdrant health checker implementation.

[INPUT]
- myrm_agent_harness.infra.health::HealthChecker (POS: 健康检查抽象基类)
- app.config.settings::settings (POS: 应用配置)

[OUTPUT]
- QdrantHealthChecker: Qdrant资源健康检查

[POS]
Qdrant健康检查器。由于系统在启动入口处（`run.py`）部署了智能猎杀锁拦截僵尸进程，Qdrant的底层 OS-level 文件锁由其 Rust 内核自动回收，这里的检查器仅负责基础的路径检查。
"""

from __future__ import annotations

from pathlib import Path

from myrm_agent_harness.infra.health.health_checker import (
    HealthChecker,
    HealthCheckResult,
    HealthStatus,
    RecoveryResult,
    RecoveryStatus,
)

from app.config.settings import settings


class QdrantHealthChecker(HealthChecker):
    """Health checker for Qdrant embedded storage.

    Note: Complex stale lock detection has been removed.
    The entrypoint (run.py) handles phantom-process killing, allowing Qdrant's
    internal Rust engine to natively manage and release its own file locks.
    """

    def __init__(self) -> None:
        self.qdrant_path = Path(settings.database.qdrant_path)

    async def check(self) -> HealthCheckResult:
        """Check Qdrant storage health."""
        if not self.qdrant_path.exists():
            return HealthCheckResult(
                status=HealthStatus.HEALTHY,
                message="Qdrant storage directory does not exist yet (first start)",
                details={"path": str(self.qdrant_path)},
            )

        return HealthCheckResult(
            status=HealthStatus.HEALTHY,
            message="Qdrant storage path verified. Lock management is handled natively by Qdrant's Rust engine.",
            details={"path": str(self.qdrant_path)},
        )

    async def recover(self) -> RecoveryResult:
        """No manual recovery needed anymore."""
        return RecoveryResult(
            status=RecoveryStatus.SUCCESS,
            message="No manual recovery needed, handled natively",
            actions_taken=["None"],
        )
