"""Unit tests for DataIsolationProbeService in server."""

from __future__ import annotations

from myrm_agent_harness.core.security.data_isolation_probes import (
    TenantMemoryContext,
)

from app.services.security.data_isolation_probe_service import (
    DataIsolationProbeService,
    get_data_isolation_probe_service,
)


def test_service_singleton_and_custom_instance() -> None:
    """Test singleton and custom service instantiation."""
    s1 = get_data_isolation_probe_service()
    s2 = get_data_isolation_probe_service()
    assert s1 is s2

    custom = DataIsolationProbeService(enforce_strict_clean=False)
    assert custom.firewall is not None


def test_service_compile_and_validate_access() -> None:
    """Test partition key compilation and record access check."""
    service = DataIsolationProbeService()
    ctx_1 = TenantMemoryContext(
        user_id="tenant_001",
        agent_id="bot_a",
        scope="session",
    )
    ctx_2 = TenantMemoryContext(
        user_id="tenant_002",
        agent_id="bot_a",
        scope="session",
    )

    spec_1 = service.compile_partition_key(ctx_1)
    assert spec_1.composite_key == "usr_tenant_001::agt_bot_a::scp_session"
    assert len(spec_1.namespace_digest) == 16

    # Valid access for same tenant
    assert service.validate_record_access(spec_1.composite_key, ctx_1) is True
    # Blocked access for different tenant
    assert service.validate_record_access(spec_1.composite_key, ctx_2) is False


def test_service_run_isolation_audit() -> None:
    """Test running adversarial isolation audit to generate Data Sovereignty Report."""
    service = DataIsolationProbeService()
    ctx = TenantMemoryContext(
        user_id="enterprise_client_x",
        agent_id="analyst_agent",
        scope="agent",
    )

    report = service.run_isolation_audit(
        context=ctx,
        environment_type="cloud_dedicated_sandbox",
    )

    assert report.is_safe is True
    assert report.total_probes_run >= 4
    assert report.cross_hits_count == 0
    assert report.isolation_pass_rate == 100.0
    assert report.partition_integrity_verified is True
    assert report.environment_type == "cloud_dedicated_sandbox"
    assert "Zero cross-contamination confirmed" in report.summary
