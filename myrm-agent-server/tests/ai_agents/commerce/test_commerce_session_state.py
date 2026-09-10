"""Tests for server-side commerce session state isolation and management.

Covers:
- ShoppingSessionState isolation from MerchantSessionState
- Session collision prevention (cannot access storefront session as merchant and vice-versa)
- Product browsing history tracking
- Staged change linking for merchant audits
"""

import pytest

from app.ai_agents.commerce.session_state import (
    CommerceSessionManager,
    CommerceSessionScopeError,
)
from myrm_agent_harness.backends.commerce.types import CommerceRole


def test_session_role_isolation() -> None:
    manager = CommerceSessionManager()

    # Create shopper session
    shopper_state = manager.get_or_create_shopping_session("sess_shopper_01", customer_id="cust_123")
    assert shopper_state.session_id == "sess_shopper_01"
    assert shopper_state.customer_id == "cust_123"
    assert manager.get_session_role("sess_shopper_01") == CommerceRole.STOREFRONT

    # Attempting to access shopper session as merchant must raise CommerceSessionScopeError
    with pytest.raises(CommerceSessionScopeError):
        manager.get_or_create_merchant_session("sess_shopper_01", merchant_id="m_001")


def test_merchant_session_isolation() -> None:
    manager = CommerceSessionManager()

    # Create merchant session
    merchant_state = manager.get_or_create_merchant_session("sess_merchant_01", merchant_id="m_001")
    assert merchant_state.session_id == "sess_merchant_01"
    assert merchant_state.merchant_id == "m_001"
    assert manager.get_session_role("sess_merchant_01") == CommerceRole.MERCHANT

    # Attempting to access merchant session as shopper must raise CommerceSessionScopeError
    with pytest.raises(CommerceSessionScopeError):
        manager.get_or_create_shopping_session("sess_merchant_01")


def test_browsing_history_tracking() -> None:
    manager = CommerceSessionManager()
    session_id = "sess_shopper_02"

    manager.record_viewed_product(session_id, "prod_01")
    manager.record_viewed_product(session_id, "prod_02")
    manager.record_viewed_product(session_id, "prod_01")  # Deduplicates and moves to top

    state = manager.get_or_create_shopping_session(session_id)
    assert state.last_viewed_product_ids == ("prod_01", "prod_02")


def test_attach_staged_change() -> None:
    manager = CommerceSessionManager()
    session_id = "sess_merchant_02"
    manager.get_or_create_merchant_session(session_id, merchant_id="m_002")

    updated = manager.attach_staged_change(session_id, "stg_123456")
    assert updated.staged_change_ids == ("stg_123456",)

    # Duplicates are ignored
    updated_again = manager.attach_staged_change(session_id, "stg_123456")
    assert updated_again.staged_change_ids == ("stg_123456",)
