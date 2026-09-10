"""Commerce Session State and Isolation Models.

[INPUT]
- pydantic::BaseModel, Field
- myrm_agent_harness.backends.commerce.types::ShoppingSessionContext, MerchantSessionContext, Cart, StagedChange

[OUTPUT]
- ShoppingSessionState: 消费者端会话状态
- MerchantSessionState: 商家端会话状态
- CommerceRole: 商业角色枚举 ("storefront" | "merchant")
- CommerceSessionManager: 双端会话状态生命周期与隔离管理器

[POS]
Server-level session state isolation layer for transactional commerce agents.
Ensures zero-crossover between customer shopping carts and merchant staging buffers.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

from myrm_agent_harness.backends.commerce.exceptions import CommerceError
from myrm_agent_harness.backends.commerce.types import (
    Cart,
    MerchantSessionContext,
    ShoppingSessionContext,
    StagedChange,
)

CommerceRole = Literal["storefront", "merchant"]


class ShoppingSessionState(BaseModel):
    """Isolated session state for customer shopping journeys."""

    context: ShoppingSessionContext
    cart: Cart = Field(default_factory=Cart)
    viewed_product_ids: list[str] = Field(default_factory=list, description="Recently viewed products")
    active_intent: str | None = Field(default=None, description="Current shopping stage: search, compare, cart, policy")
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_activity_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def record_view(self, product_id: str) -> None:
        """Track viewed products with deduplication."""
        if product_id not in self.viewed_product_ids:
            self.viewed_product_ids.append(product_id)
        self.last_activity_at = datetime.now(timezone.utc).isoformat()


class MerchantSessionState(BaseModel):
    """Isolated session state for back-office staff operations."""

    context: MerchantSessionContext
    staged_changes: list[StagedChange] = Field(default_factory=list, description="Pending proposal changes")
    inspected_listing_id: str | None = Field(default=None, description="Listing currently being evaluated")
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_activity_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def add_staged_change(self, change: StagedChange) -> None:
        """Stage a new proposal into the session buffer."""
        self.staged_changes.append(change)
        self.last_activity_at = datetime.now(timezone.utc).isoformat()

    def get_staged_change(self, change_id: str) -> StagedChange | None:
        """Look up a staged change by ID."""
        return next((c for c in self.staged_changes if c.change_id == change_id), None)


class CommerceSessionManager:
    """Thread-safe state isolation manager for dual-role commerce sessions."""

    def __init__(self) -> None:
        self._shopping_sessions: dict[str, ShoppingSessionState] = {}
        self._merchant_sessions: dict[str, MerchantSessionState] = {}
        self._lock = threading.Lock()

    def get_or_create_shopping_session(
        self,
        session_id: str,
        customer_id: str = "guest",
        currency: str = "USD",
        locale: str = "en-US",
    ) -> ShoppingSessionState:
        with self._lock:
            if session_id in self._merchant_sessions:
                raise CommerceError(
                    f"Session {session_id} is already registered as a merchant session. Role crossover prohibited.",
                    code="ROLE_CROSSOVER_PROHIBITED",
                )
            if session_id not in self._shopping_sessions:
                ctx = ShoppingSessionContext(
                    session_id=session_id,
                    customer_id=customer_id,
                    currency=currency,
                    locale=locale,
                )
                self._shopping_sessions[session_id] = ShoppingSessionState(context=ctx)
            return self._shopping_sessions[session_id]

    def get_or_create_merchant_session(
        self,
        session_id: str,
        operator_id: str,
        merchant_id: str,
        roles: list[str] | None = None,
    ) -> MerchantSessionState:
        with self._lock:
            if session_id in self._shopping_sessions:
                raise CommerceError(
                    f"Session {session_id} is already registered as a shopping session. Role crossover prohibited.",
                    code="ROLE_CROSSOVER_PROHIBITED",
                )
            if session_id not in self._merchant_sessions:
                ctx = MerchantSessionContext(
                    session_id=session_id,
                    operator_id=operator_id,
                    merchant_id=merchant_id,
                    roles=roles or ["operator"],
                )
                self._merchant_sessions[session_id] = MerchantSessionState(context=ctx)
            return self._merchant_sessions[session_id]

    def get_session_role(self, session_id: str) -> CommerceRole | None:
        with self._lock:
            if session_id in self._shopping_sessions:
                return "storefront"
            if session_id in self._merchant_sessions:
                return "merchant"
            return None

    def close_session(self, session_id: str) -> None:
        with self._lock:
            self._shopping_sessions.pop(session_id, None)
            self._merchant_sessions.pop(session_id, None)
