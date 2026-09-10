"""Unit tests for Server GatedStorefrontService."""

from __future__ import annotations

import pytest
from myrm_agent_harness.backends.commerce.gates import CartCapLimits
from myrm_agent_harness.backends.commerce.memory_backend import InMemoryStorefrontBackend
from myrm_agent_harness.backends.commerce.types import (
    Product,
    ProductVariant,
    VariantOption,
)

from app.commerce.gates_service import GatedStorefrontService


@pytest.fixture
def test_backend() -> InMemoryStorefrontBackend:
    sneaker = Product(
        product_id="prod_runner",
        title="Speed Runner",
        description="Lightweight running shoes",
        base_price=99.0,
        category="shoes",
        in_stock=True,
        variants=(
            ProductVariant(
                variant_id="var_red_42",
                title="Red / 42",
                price=99.0,
                in_stock=True,
                options=(
                    VariantOption(name="Color", value="Red"),
                    VariantOption(name="Size", value="42"),
                ),
            ),
            ProductVariant(
                variant_id="var_blue_42",
                title="Blue / 42",
                price=105.0,
                in_stock=False,  # OOS
                options=(
                    VariantOption(name="Color", value="Blue"),
                    VariantOption(name="Size", value="42"),
                ),
            ),
        ),
    )
    return InMemoryStorefrontBackend(products=[sneaker])


@pytest.mark.asyncio
async def test_gated_add_held_when_options_unspecified(test_backend: InMemoryStorefrontBackend) -> None:
    service = GatedStorefrontService(backend=test_backend)
    receipt = await service.execute_gated_add_to_cart(
        session_id="session_alice",
        product_id="prod_runner",
        quantity=1,
    )

    assert receipt.status == "held"
    assert "Color" in receipt.suggestion_chips
    assert "Size" in receipt.suggestion_chips
    assert "Options not fully specified" in str(receipt.gate_reason)


@pytest.mark.asyncio
async def test_gated_add_blocked_when_variant_oos(test_backend: InMemoryStorefrontBackend) -> None:
    service = GatedStorefrontService(backend=test_backend)
    receipt = await service.execute_gated_add_to_cart(
        session_id="session_alice",
        product_id="prod_runner",
        quantity=1,
        selected_options={"Color": "Blue", "Size": "42"},
    )

    assert receipt.status == "blocked"
    assert "out of stock" in str(receipt.gate_reason).lower()


@pytest.mark.asyncio
async def test_gated_add_success_id_only_receipt(test_backend: InMemoryStorefrontBackend) -> None:
    service = GatedStorefrontService(backend=test_backend)
    receipt = await service.execute_gated_add_to_cart(
        session_id="session_alice",
        product_id="prod_runner",
        quantity=2,
        selected_options={"Color": "Red", "Size": "42"},
    )

    assert receipt.status == "success"
    assert receipt.product_id == "prod_runner"
    assert receipt.variant_id == "var_red_42"
    assert receipt.quantity == 2
    assert receipt.unit_price == 99.0
    assert receipt.subtotal == 198.0
    # Confirm ID-only fencing: Title text is not stored on receipt
    assert not hasattr(receipt, "title")


@pytest.mark.asyncio
async def test_gated_add_blocked_by_cart_cap(test_backend: InMemoryStorefrontBackend) -> None:
    tight_limits = CartCapLimits(max_quantity_per_item=3, max_cart_lines=5, max_total_quantity=10)
    service = GatedStorefrontService(backend=test_backend, limits=tight_limits)

    # Adding 5 exceeds max_quantity_per_item (3)
    receipt = await service.execute_gated_add_to_cart(
        session_id="session_bob",
        product_id="prod_runner",
        quantity=5,
        selected_options={"Color": "Red", "Size": "42"},
    )

    assert receipt.status == "blocked"
    assert "Per-item cap exceeded" in str(receipt.gate_reason)
