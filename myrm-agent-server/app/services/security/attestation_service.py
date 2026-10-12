"""[INPUT]
- myrm_agent_harness.agent.security.attestation::EnvironmentAttestationEngine, AttestationConfig, EnvironmentAttestationReport (POS: 框架层全向量自检引擎)

[OUTPUT]
- AttestationService: 业务层环境防篡改认证与可信徽章服务

[POS]
提供宿主隔离、挂载边界、二进制签名与外联 TLS 证书真实性的统一体检管理，支持前端可信徽章展示与执行前硬熔断。
"""

from __future__ import annotations

import logging
import threading
from typing import ClassVar

from myrm_agent_harness.agent.security.attestation import (
    AttestationConfig,
    EnvironmentAttestationEngine,
    EnvironmentAttestationReport,
)

logger = logging.getLogger(__name__)


class AttestationService:
    """Service managing runtime environment attestation and trust verification."""

    _lock = threading.Lock()
    _latest_report: ClassVar[EnvironmentAttestationReport | None] = None

    @classmethod
    def get_latest_report(cls) -> EnvironmentAttestationReport:
        """Obtain latest attestation report or perform an initial baseline audit."""
        with cls._lock:
            if cls._latest_report is None:
                cls._latest_report = EnvironmentAttestationEngine.run_preflight_audit()
            return cls._latest_report

    @classmethod
    def verify_environment(
        cls,
        config: AttestationConfig | None = None,
    ) -> EnvironmentAttestationReport:
        """Force a fresh on-demand all-vector attestation audit and update cache."""
        report = EnvironmentAttestationEngine.run_preflight_audit(config)
        with cls._lock:
            cls._latest_report = report
        logger.info(
            "[ATTESTATION_SERVICE] Refreshed runtime attestation report: passed=%s, summary=%s",
            report.overall_passed,
            report.summary,
        )
        return report

    @classmethod
    def assert_runtime_trusted(
        cls,
        config: AttestationConfig | None = None,
    ) -> EnvironmentAttestationReport:
        """Assert runtime security environment is trusted; raises on critical anomalies."""
        report = EnvironmentAttestationEngine.assert_attestation_passed(config)
        with cls._lock:
            cls._latest_report = report
        return report

    @classmethod
    def clear_cache(cls) -> None:
        """Clear cached report for test isolation."""
        with cls._lock:
            cls._latest_report = None
