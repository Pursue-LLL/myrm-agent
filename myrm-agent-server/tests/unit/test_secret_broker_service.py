"""Unit tests for SecretBrokerService in server layer.

[POS]
Server unit tests verifying secret ingestion, egress-bound substitution,
and atomic one-shot operation grant management.
"""

from __future__ import annotations

import pytest
from myrm_agent_harness.core.security.secret_broker import (
    AtomicGrantInvalidatedError,
    EgressHostMismatchError,
)

from app.services.security.secret_broker_service import SecretBrokerService


def test_secret_broker_service_ingest_and_egress() -> None:
    service = SecretBrokerService()

    # Ingest secret
    handle = service.ingest_secret(
        secret_name="OPENAI_API_KEY",
        secret_value="sk-proj-test1234567890",
        allowed_host="api.openai.com",
    )
    assert handle.handle_id.startswith("hnd_")
    assert handle.allowed_host == "api.openai.com"
    assert handle.placeholder == f"{{{{SECRET_VAULT:{handle.handle_id}}}}}"

    # Verify listing
    handles = service.list_handles()
    assert any(h.handle_id == handle.handle_id for h in handles)

    # Authorized egress
    payload = f"Bearer {handle.placeholder}"
    res = service.resolve_egress(content=payload, target_host="api.openai.com")
    assert res.authorized is True
    assert res.replacements_count == 1
    assert res.resolved_content == "Bearer sk-proj-test1234567890"

    # Mismatched egress raises EgressHostMismatchError
    with pytest.raises(EgressHostMismatchError):
        service.resolve_egress(content=payload, target_host="api.untrusted-ai.com")


def test_secret_broker_service_atomic_grant_flow() -> None:
    service = SecretBrokerService()

    op_payload = {"user_id": "usr_999", "role": "admin"}
    grant = service.create_grant(
        operation_name="promote_user",
        payload=op_payload,
        ttl_seconds=60.0,
    )
    assert grant.status == "pending"

    # Approve
    approved = service.approve_grant(grant.grant_id)
    assert approved.status == "granted"

    # Consume successfully
    consumed = service.consume_grant(grant.grant_id, "promote_user", op_payload)
    assert consumed is True

    # Double consume rejected
    with pytest.raises(AtomicGrantInvalidatedError):
        service.consume_grant(grant.grant_id, "promote_user", op_payload)


def test_secret_broker_service_rejection() -> None:
    service = SecretBrokerService()

    op_payload = {"action": "drop_table", "table": "payments"}
    grant = service.create_grant(
        operation_name="db_drop",
        payload=op_payload,
    )
    # Reject
    rejected = service.reject_grant(grant.grant_id, reason="Security review denied")
    assert rejected.status == "revoked"

    # Consumption rejected
    with pytest.raises(AtomicGrantInvalidatedError):
        service.consume_grant(grant.grant_id, "db_drop", op_payload)
