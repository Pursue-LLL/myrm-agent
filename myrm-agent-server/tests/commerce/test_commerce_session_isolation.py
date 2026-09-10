"""Unit tests for Server Commerce Session Isolation and Lifecycle Management."""

from __future__ import annotations

import pytest
from myrm_agent_harness.backends.commerce.exceptions import CommerceError
from myrm_agent_harness.backends.commerce.types import StagedChange

from app.commerce import (
    CommerceSessionManager,
    MerchantSessionState,
    ShoppingSessionState,
)


def test_shopping_session_lifecycle() -> None:
    manager = CommerceSessionManager()
    session = manager.get_or_create_shopping_session(
        session_id="shop_123",
        customer_id="cust_alice",
        currency="USD",
    )

    assert isinstance(session, ShoppingSessionState)
    assert session.context.customer_id == "cust_alice"
    assert session.cart.total_price_cents == 0

    # View record
    session.record_view("prod_phone")
    session.record_view("prod_phone")  # Deduplication
    assert session.viewed_product_ids == ["prod_phone"]

    # Role detection
    assert manager.get_session_role("shop_123") == "storefront"


def test_merchant_session_lifecycle() -> None:
    manager = CommerceSessionManager()
    session = manager.get_or_create_merchant_session(
        session_id="merch_456",
        operator_id="op_bob",
        merchant_id="store_main",
        roles=["manager"],
    )

    assert isinstance(session, MerchantSessionState)
    assert session.context.operator_id == "op_bob"
    assert len(session.staged_changes) == 0

    # Add staged change
    staged = StagedChange(
        change_id="stage_001",
        listing_id="list_phone",
        change_type="price_update",
        payload={"new_price": "89900"},
    )
    session.add_staged_change(staged)
    assert len(session.staged_changes) == 1
    assert session.get_staged_change("stage_001") == staged

    # Role detection
    assert manager.get_session_role("merch_456") == "merchant"


def test_role_crossover_prohibition() -> None:
    manager = CommerceSessionManager()
    manager.get_or_create_shopping_session("sess_conflict_1")

    # Cannot acquire same session ID as merchant
    with pytest.raises(CommerceError) as exc_info:
        manager.get_or_create_merchant_session(
            session_id="sess_conflict_1",
            operator_id="op_mallory",
            merchant_id="store_main",
        )
    assert exc_info.value.code == "ROLE_CROSSOVER_PROHIBITED"

    manager.get_or_create_merchant_session(
        session_id="sess_conflict_2",
        operator_id="op_mallory",
        merchant_id="store_main",
    )

    # Cannot acquire same session ID as shopping session
    with pytest.raises(CommerceError) as exc_info:
        manager.get_or_create_shopping_session("sess_conflict_2")
    assert exc_info.value.code == "ROLE_CROSSOVER_PROHIBITED"


def test_session_cleanup() -> None:
    manager = CommerceSessionManager()
    manager.get_or_create_shopping_session("temp_sess")
    assert manager.get_session_role("temp_sess") == "storefront"

    manager.close_session("temp_sess")
    assert manager.get_session_role("temp_sess") is None
