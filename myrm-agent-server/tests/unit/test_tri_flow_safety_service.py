"""Unit tests for TriFlowSafetyService in server."""

from __future__ import annotations

from myrm_agent_harness.core.security.tri_flow_isolation import (
    DocumentedEndpointSpec,
    ToolRoleContract,
)

from app.services.security.tri_flow_safety_service import (
    TriFlowSafetyService,
    get_tri_flow_safety_service,
)


def test_service_singleton_and_custom_instance() -> None:
    """Test singleton access and custom instance creation."""
    s1 = get_tri_flow_safety_service()
    s2 = get_tri_flow_safety_service()
    assert s1 is s2

    custom = TriFlowSafetyService(enforce_strict_endpoints=False)
    assert custom is not None


def test_service_tri_flow_role_boundaries() -> None:
    """Test role boundary enforcement through service layer."""
    service = TriFlowSafetyService()

    # 1. Read-Only role executing allowed read tool
    r1 = service.validate_tool_call(role="read_only", tool_name="web_search")
    assert r1.is_allowed is True
    assert r1.requires_hitl is False

    # 2. Read-Only role attempting to execute financial buyer tool
    r2 = service.validate_tool_call(role="read_only", tool_name="create_order")
    assert r2.is_allowed is False
    assert "Violation: tool 'create_order' requires roles" in r2.reason

    # 3. Buyer role calling financial tool with threshold check
    r3_unconfirmed = service.validate_tool_call(
        role="buyer",
        tool_name="create_order",
        amount=100.0,
        hitl_confirmed=False,
    )
    assert r3_unconfirmed.is_allowed is False
    assert r3_unconfirmed.requires_hitl is True

    r3_confirmed = service.validate_tool_call(
        role="buyer",
        tool_name="create_order",
        amount=100.0,
        hitl_confirmed=True,
    )
    assert r3_confirmed.is_allowed is True


def test_service_custom_tool_contract_registration() -> None:
    """Test registering custom tool contracts."""
    service = TriFlowSafetyService()
    service.register_tool_contract(
        ToolRoleContract(
            tool_name="custom_seller_invoice",
            allowed_roles=("seller",),
            is_financial_transaction=True,
        )
    )

    # Seller can invoke it
    res_seller = service.validate_tool_call(
        role="seller", tool_name="custom_seller_invoice"
    )
    assert res_seller.is_allowed is True

    # Buyer cannot invoke it
    res_buyer = service.validate_tool_call(
        role="buyer", tool_name="custom_seller_invoice"
    )
    assert res_buyer.is_allowed is False


def test_service_endpoint_validator_and_sanitization() -> None:
    """Test zero-guesswork endpoint validation and log sanitization."""
    service = TriFlowSafetyService()
    service.register_endpoint_spec(
        DocumentedEndpointSpec(
            service="crypto_exchange",
            path="/v1/ticker/{symbol}",
            allowed_methods=("GET",),
        )
    )

    # Allowed endpoint
    res_ep_ok = service.validate_endpoint_call(
        service="crypto_exchange",
        path="/v1/ticker/BTCUSDT",
        method="GET",
    )
    assert res_ep_ok.is_allowed is True

    # Guessing undocumented endpoint
    res_ep_blocked = service.validate_endpoint_call(
        service="crypto_exchange",
        path="/v1/admin/dump_wallets",
        method="POST",
    )
    assert res_ep_blocked.is_allowed is False

    # Sanitization
    dirty_log = "Fatal error with private key 0x11223344556677889900aabbccddeeff11223344556677889900aabbccddeeff"
    clean_res = service.sanitize_text(dirty_log)
    assert clean_res.redactions_count == 1
    assert "0x11223344556677889900aabbccddeeff11223344556677889900aabbccddeeff" not in clean_res.sanitized_text
    assert "[REDACTED_CREDENTIAL:ethereum_private_key:" in clean_res.sanitized_text
