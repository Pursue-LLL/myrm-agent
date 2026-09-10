"""Cart Governance Service for transactional commerce agents.

[INPUT]
- myrm_agent_harness.backends.commerce.types::Product, ProductVariant, Cart, CartLine, VariantOption
- myrm_agent_harness.backends.commerce.protocols::StorefrontBackendProtocol
- myrm_agent_harness.backends.commerce.gates::CartCapLimits, CartOperationReceipt, CartSessionLock, check_cart_cap, resolve_variant_options
- myrm_agent_harness.backends.commerce.exceptions::CommerceError, OptionsResolutionHeld, CartCapExceeded, Unavailable
- app.commerce.session_state::CommerceSessionManager

[OUTPUT]
- CartGovernanceService: 生产级服务端加车风控与变体收敛门禁服务
- GatedCartResult: 包含门禁决策状态与结构化回执的业务响应对象

[POS]
Server-level coordinator orchestrating option convergence and cart cap enforcement.
Guarantees id-only confirmations, option held states, and per-session serialized mutations.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from myrm_agent_harness.backends.commerce.exceptions import (
    CartCapExceeded,
    CommerceError,
    OptionsResolutionHeld,
    Unavailable,
)
from myrm_agent_harness.backends.commerce.gates import (
    CartCapLimits,
    CartOperationReceipt,
    CartSessionLock,
    check_cart_cap,
    resolve_variant_options,
)
from myrm_agent_harness.backends.commerce.protocols import StorefrontBackendProtocol
from myrm_agent_harness.backends.commerce.types import Product, VariantOption

from app.commerce.session_state import CommerceSessionManager

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class GatedCartResult:
    """Business result of a gated add-to-cart operation."""

    success: bool
    status: str  # "success" | "held" | "blocked"
    receipt: CartOperationReceipt
    message: str


class CartGovernanceService:
    """Service enforcing OPTIONS_GATE, Cart Cap Limits, and Id-Only Fencing."""

    def __init__(
        self,
        backend: StorefrontBackendProtocol,
        session_manager: CommerceSessionManager,
        limits: CartCapLimits | None = None,
    ) -> None:
        self._backend = backend
        self._session_manager = session_manager
        self._limits = limits or CartCapLimits()
        self._session_lock = CartSessionLock()

    async def execute_gated_add_to_cart(
        self,
        session_id: str,
        product_id: str,
        quantity: int = 1,
        *,
        selected_options: dict[str, str] | None = None,
        explicit_variant_id: str | None = None,
    ) -> GatedCartResult:
        """Execute add-to-cart protected by Options Resolution Gate and Cap Governance.

        Step 1: Acquire session-level lock to serialize writes.
        Step 2: Fetch full product details.
        Step 3: Run resolve_variant_options. If HELD, return suggestion chips without modifying cart.
        Step 4: Check cart capacity and per-item limits. If breached, block and return violation.
        Step 5: Perform physical write to backend.
        Step 6: Return sanitized, Id-only CartOperationReceipt (titles stripped to avoid prompt injection).
        """
        async with self._session_lock.get_lock(session_id):
            # Ensure shopping session exists
            shopping_state = self._session_manager.get_or_create_shopping_session(session_id=session_id)

            # Retrieve product details
            product = await self._backend.get_product_details(product_id)
            if not product:
                receipt = CartOperationReceipt(
                    status="blocked",
                    cart_id=session_id,
                    item_id=product_id,
                    gate_reason=f"Product '{product_id}' not found in catalog.",
                )
                return GatedCartResult(
                    success=False,
                    status="blocked",
                    receipt=receipt,
                    message=f"Product '{product_id}' not found.",
                )

            # Track view in session state
            shopping_state.record_view(product_id)

            # 1. Evaluate OPTIONS_GATE
            resolution = resolve_variant_options(
                product=product,
                selected_options=selected_options,
                explicit_variant_id=explicit_variant_id,
            )

            if resolution.decision == "held":
                receipt = CartOperationReceipt(
                    status="held",
                    cart_id=session_id,
                    item_id=product_id,
                    gate_reason=resolution.reason,
                    suggestion_chips=resolution.suggestion_chips,
                )
                return GatedCartResult(
                    success=False,
                    status="held",
                    receipt=receipt,
                    message=resolution.reason,
                )

            if resolution.decision == "blocked":
                receipt = CartOperationReceipt(
                    status="blocked",
                    cart_id=session_id,
                    item_id=product_id,
                    variant_id=resolution.resolved_variant_id,
                    gate_reason=resolution.reason,
                    suggestion_chips=resolution.suggestion_chips,
                )
                return GatedCartResult(
                    success=False,
                    status="blocked",
                    receipt=receipt,
                    message=resolution.reason,
                )

            # 2. Evaluate CAP_GOVERNANCE
            current_cart = await self._backend.get_cart(session_id)
            target_variant_id = resolution.resolved_variant_id

            cap_check = check_cart_cap(
                current_cart=current_cart,
                variant_id=target_variant_id,
                adding_quantity=quantity,
                limits=self._limits,
            )

            if not cap_check.allowed:
                receipt = CartOperationReceipt(
                    status="blocked",
                    cart_id=session_id,
                    item_id=product_id,
                    variant_id=target_variant_id,
                    gate_reason=cap_check.reason,
                )
                return GatedCartResult(
                    success=False,
                    status="blocked",
                    receipt=receipt,
                    message=cap_check.reason or "Cart capacity limit exceeded.",
                )

            # 3. Perform backend mutation
            # Build options tuple if specified
            opts_tuple: tuple[VariantOption, ...] = ()
            if selected_options:
                opts_tuple = tuple(VariantOption(name=k, value=v) for k, v in selected_options.items())

            update_res = await self._backend.add_to_cart(
                session_id=session_id,
                product_id=product_id,
                variant_id=target_variant_id,
                quantity=quantity,
                selected_options=opts_tuple,
            )

            # Synchronize server session cart representation
            shopping_state.cart = update_res.cart

            # Locate modified line for pricing
            mod_line = next((line for line in update_res.cart.lines if line.line_id == update_res.modified_line_id), None)
            unit_price_cents = int(round(mod_line.unit_price * 100)) if mod_line else 0
            total_price_cents = int(round(mod_line.unit_price * mod_line.quantity * 100)) if mod_line else 0

            # 4. Construct Id-Only Receipt (No catalog titles echoed)
            receipt = CartOperationReceipt(
                status="success",
                cart_id=session_id,
                item_id=product_id,
                variant_id=target_variant_id,
                quantity=quantity,
                unit_price_cents=unit_price_cents,
                total_price_cents=total_price_cents,
                gate_reason=None,
            )

            return GatedCartResult(
                success=True,
                status="success",
                receipt=receipt,
                message=f"Added {quantity} unit(s) of variant '{target_variant_id or product_id}' to cart.",
            )
