"""Commerce Server Gated Storefront Service.

[INPUT]
- myrm_agent_harness.backends.commerce.protocols::StorefrontBackendProtocol
- myrm_agent_harness.backends.commerce.types::Product, Cart, CartLine, VariantOption
- myrm_agent_harness.backends.commerce.gates::(
    CartCapLimits, CartOperationReceipt, CartSessionLock,
    check_cart_cap, resolve_variant_options,
  )
- app.commerce.session_state::CommerceSessionManager

[OUTPUT]
- GatedStorefrontService: 整合多规格收敛门禁 (OPTIONS_GATE)、购物车限额防御与会话锁的安全加车服务

[POS]
Server-level transactional coordinator for safe storefront operations.
Prevents un-converged variant adds, blocks quota overflows, and fences untrusted catalog titles.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from myrm_agent_harness.backends.commerce.gates import (
    CartCapLimits,
    CartOperationReceipt,
    CartSessionLock,
    check_cart_cap,
    resolve_variant_options,
)

if TYPE_CHECKING:
    from myrm_agent_harness.backends.commerce.protocols import StorefrontBackendProtocol
    from myrm_agent_harness.backends.commerce.types import VariantOption


class GatedStorefrontService:
    """High-reliability coordinator enforcing variant gates and cart cap governance."""

    def __init__(
        self,
        backend: StorefrontBackendProtocol,
        limits: CartCapLimits | None = None,
    ) -> None:
        self._backend = backend
        self._limits = limits or CartCapLimits()
        self._session_locks = CartSessionLock()

    async def execute_gated_add_to_cart(
        self,
        session_id: str,
        product_id: str,
        quantity: int = 1,
        selected_options: tuple[VariantOption, ...] | dict[str, str] | None = None,
        explicit_variant_id: str | None = None,
    ) -> CartOperationReceipt:
        """Execute add-to-cart protected by OPTIONS_GATE, CAP_GOVERNANCE, and session lock."""
        # 1. Fetch product record
        product = await self._backend.get_product_details(product_id)
        if not product or not product.in_stock:
            return CartOperationReceipt(
                status="blocked",
                cart_id=f"cart_{session_id}",
                product_id=product_id,
                gate_reason=f"Product '{product_id}' is unavailable or does not exist.",
            )

        # 2. Evaluate OPTIONS_GATE
        resolution = resolve_variant_options(
            product,
            selected_options=selected_options,
            explicit_variant_id=explicit_variant_id,
        )

        if resolution.decision == "held":
            return CartOperationReceipt(
                status="held",
                cart_id=f"cart_{session_id}",
                product_id=product_id,
                gate_reason=resolution.reason,
                suggestion_chips=resolution.suggestion_chips,
            )

        if resolution.decision == "blocked":
            return CartOperationReceipt(
                status="blocked",
                cart_id=f"cart_{session_id}",
                product_id=product_id,
                gate_reason=resolution.reason,
                suggestion_chips=resolution.suggestion_chips,
            )

        target_variant_id = resolution.resolved_variant_id

        # 3. Acquire session lock and evaluate CAP_GOVERNANCE
        lock = self._session_locks.get_lock(session_id)
        async with lock:
            current_cart = await self._backend.get_cart(session_id)
            cap_check = check_cart_cap(
                current_cart=current_cart,
                variant_id=target_variant_id,
                adding_quantity=quantity,
                limits=self._limits,
            )

            if not cap_check.allowed:
                return CartOperationReceipt(
                    status="blocked",
                    cart_id=current_cart.cart_id,
                    product_id=product_id,
                    variant_id=target_variant_id,
                    quantity=quantity,
                    gate_reason=cap_check.reason,
                )

            # 4. Perform actual mutation on underlying backend
            # Note: selected_options is passed if available
            variant_options_tuple: tuple[VariantOption, ...] = ()
            if isinstance(selected_options, tuple):
                variant_options_tuple = selected_options

            update_result = await self._backend.add_to_cart(
                session_id=session_id,
                product_id=product_id,
                quantity=quantity,
                variant_id=target_variant_id,
                selected_options=variant_options_tuple,
            )

            # 5. Build ID-only receipt (Catalog titles are strictly fenced)
            modified_line = None
            if update_result.modified_line_id:
                for line in update_result.cart.lines:
                    if line.line_id == update_result.modified_line_id:
                        modified_line = line
                        break

            unit_price = modified_line.unit_price if modified_line else 0.0
            line_qty = modified_line.quantity if modified_line else quantity

            return CartOperationReceipt(
                status="success",
                cart_id=update_result.cart_id,
                line_id=update_result.modified_line_id,
                product_id=product_id,
                variant_id=target_variant_id,
                quantity=line_qty,
                unit_price=unit_price,
                subtotal=update_result.cart.subtotal,
                gate_reason="Operation cleared options and capacity gates successfully.",
            )
