"""Unit tests for AirGappedService in server layer.

[POS]
Server unit tests verifying operational egress tier configuration, zero-egress cryptographic
assertion validation, and enterprise sovereign compliance dossier generation.
"""

from __future__ import annotations

import pytest
from myrm_agent_harness.core.security.air_gapped import ExternalEgressBlockedError

from app.schemas.air_gapped import SetEgressTierRequest
from app.services.security.air_gapped_service import AirGappedService


def test_air_gapped_service_tiers_and_attempts() -> None:
    service = AirGappedService()

    # 1. Default tier is air_gapped_sovereign
    status = service.get_status()
    assert status.current_tier == "air_gapped_sovereign"
    assert status.is_air_gapped is True

    # 2. Local loopback permitted
    rec_local = service.guard.record_and_assert("127.0.0.1", 11434)
    assert rec_local.allowed is True

    # 3. External connection strictly blocked
    with pytest.raises(ExternalEgressBlockedError):
        service.guard.record_and_assert("api.anthropic.com", 443)

    # 4. Check attempts telemetry
    attempts = service.list_attempts()
    assert len(attempts) == 2
    assert attempts[0].destination_host == "api.anthropic.com"
    assert attempts[0].allowed is False
    assert attempts[1].destination_host == "127.0.0.1"
    assert attempts[1].allowed is True

    # 5. Switch tier to conservative
    update_res = service.set_tier(SetEgressTierRequest(tier="conservative"))
    assert update_res.current_tier == "conservative"
    assert update_res.is_air_gapped is False


def test_air_gapped_service_compliance_dossier() -> None:
    service = AirGappedService()

    # Make only loopback connections
    service.guard.clear_attempts()
    service.guard.record_and_assert("localhost", 8000)
    service.guard.record_and_assert("127.0.0.1", 9000)

    # Generate dossier
    dossier = service.generate_compliance_dossier(organization_id="bank_client_alpha")

    assert dossier.organization_id == "bank_client_alpha"
    assert dossier.zero_egress_assertion.is_zero_egress_compliant is True
    assert dossier.zero_egress_assertion.external_egress_count == 0
    assert len(dossier.sha256_dossier_signature) == 64
    assert "GB/T" in dossier.compliance_standard
    assert "Zero outbound" in dossier.data_sovereignty_declaration
