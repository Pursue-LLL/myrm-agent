"""Service orchestrating multi-tenant data isolation and cross-contamination probes.

[INPUT]
- myrm_agent_harness.core.security.data_isolation_probes::MemoryNamespaceFirewall, CrossTenantProbeRunner

[OUTPUT]
- DataIsolationProbeService, get_data_isolation_probe_service

[POS]
Business service managing memory partition firewalls and cross-contamination probes.
"""

from __future__ import annotations

from myrm_agent_harness.core.security.data_isolation_probes import (
    CrossTenantProbeRunner,
    DataSovereigntyReport,
    MemoryNamespaceFirewall,
    PartitionKeySpec,
    TenantMemoryContext,
)


class DataIsolationProbeService:
    """Service managing memory partition firewalls and adversarial isolation audits."""

    def __init__(self, enforce_strict_clean: bool = True) -> None:
        self._firewall = MemoryNamespaceFirewall(enforce_strict_clean=enforce_strict_clean)

    @property
    def firewall(self) -> MemoryNamespaceFirewall:
        """Access underlying MemoryNamespaceFirewall."""
        return self._firewall

    def compile_partition_key(
        self,
        context: TenantMemoryContext,
    ) -> PartitionKeySpec:
        """Compile immutable composite physical partition key."""
        return self._firewall.compile_partition_key(context)

    def validate_record_access(
        self,
        record_partition_key: str,
        querying_context: TenantMemoryContext,
    ) -> bool:
        """Check if record access is within the querying context boundary."""
        return self._firewall.validate_record_access(record_partition_key, querying_context)

    def run_isolation_audit(
        self,
        context: TenantMemoryContext,
        environment_type: str = "local_standalone",
    ) -> DataSovereigntyReport:
        """Execute full synthetic cross-tenant adversarial probe battery."""
        runner = CrossTenantProbeRunner(
            firewall=self._firewall,
            environment_type=environment_type,
        )
        return runner.run_sybil_isolation_audit(current_context=context)


_singleton_probe_service: DataIsolationProbeService | None = None


def get_data_isolation_probe_service() -> DataIsolationProbeService:
    """Retrieve or initialize singleton DataIsolationProbeService."""
    global _singleton_probe_service
    if _singleton_probe_service is None:
        _singleton_probe_service = DataIsolationProbeService()
    return _singleton_probe_service
