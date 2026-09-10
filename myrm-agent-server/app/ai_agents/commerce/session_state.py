"""Commerce session state models and isolation guards for Server layer.

[INPUT]
- myrm_agent_harness.backends.commerce::CommerceRole, ShoppingSessionState, MerchantSessionState (POS: 商业会话状态 DTO)

[OUTPUT]
- CommerceSessionManager: 会话级双角色商业状态隔离管理器
- CommerceSessionScopeError: 越权跨角色操作异常

[POS]
Server-side business state management ensuring strict isolation between
shopper customer sessions and merchant back-office management sessions.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Literal

from myrm_agent_harness.backends.commerce.types import (
    CommerceRole,
    MerchantSessionState,
    ShoppingSessionState,
)


class CommerceSessionScopeError(PermissionError):
    """Raised when an operation violates commerce role session boundaries."""

    def __init__(self, message: str = "Access denied: session role mismatch.") -> None:
        super().__init__(message)


class CommerceSessionManager:
    """Manages isolated state for Storefront and Merchant agent sessions."""

    def __init__(self) -> None:
        self._shopping_sessions: dict[str, ShoppingSessionState] = {}
        self._merchant_sessions: dict[str, MerchantSessionState] = {}

    def get_or_create_shopping_session(
        self,
        session_id: str,
        customer_id: str | None = None,
    ) -> ShoppingSessionState:
        """Retrieve or initialize a storefront shopping session."""
        if session_id in self._merchant_sessions:
            raise CommerceSessionScopeError(
                f"Session {session_id} is registered as a merchant session and cannot be accessed as storefront."
            )
        if session_id not in self._shopping_sessions:
            self._shopping_sessions[session_id] = ShoppingSessionState(
                session_id=session_id,
                customer_id=customer_id,
                active_cart_id=f"cart_{session_id}",
            )
        return self._shopping_sessions[session_id]

    def get_or_create_merchant_session(
        self,
        session_id: str,
        merchant_id: str,
        authorized_permissions: tuple[str, ...] = ("read_performance", "stage_changes"),
    ) -> MerchantSessionState:
        """Retrieve or initialize a merchant management session."""
        if session_id in self._shopping_sessions:
            raise CommerceSessionScopeError(
                f"Session {session_id} is registered as a storefront session and cannot be accessed as merchant."
            )
        if session_id not in self._merchant_sessions:
            self._merchant_sessions[session_id] = MerchantSessionState(
                session_id=session_id,
                merchant_id=merchant_id,
                authorized_permissions=authorized_permissions,
            )
        return self._merchant_sessions[session_id]

    def get_session_role(self, session_id: str) -> CommerceRole | None:
        """Determine the commerce role bound to the session."""
        if session_id in self._shopping_sessions:
            return CommerceRole.STOREFRONT
        if session_id in self._merchant_sessions:
            return CommerceRole.MERCHANT
        return None

    def record_viewed_product(self, session_id: str, product_id: str) -> ShoppingSessionState:
        """Update recent browsing history for a shopping session."""
        state = self.get_or_create_shopping_session(session_id)
        current = list(state.last_viewed_product_ids)
        if product_id in current:
            current.remove(product_id)
        current.insert(0, product_id)
        # Keep recent 10 products
        updated = replace(state, last_viewed_product_ids=tuple(current[:10]))
        self._shopping_sessions[session_id] = updated
        return updated

    def attach_staged_change(self, session_id: str, change_id: str) -> MerchantSessionState:
        """Link a staged change proposal to a merchant session."""
        state = self._merchant_sessions.get(session_id)
        if not state:
            raise CommerceSessionScopeError(f"Merchant session {session_id} not found.")
        current = list(state.staged_change_ids)
        if change_id not in current:
            current.append(change_id)
        updated = replace(state, staged_change_ids=tuple(current))
        self._merchant_sessions[session_id] = updated
        return updated
