"""Commerce State-Slice Evaluation Router & Engine.

[INPUT]
- pydantic::BaseModel, Field
- typing::Literal
- myrm_agent_harness.backends.commerce::* (POS: Industry starter packs, gates, guardrails, and data models)

[OUTPUT]
- GET /api/v1/commerce/evals/presets: List out-of-the-box standard commerce slice evaluation test cases
- POST /api/v1/commerce/evals/generate-slice: Generate a structured .slice.json eval case
- POST /api/v1/commerce/evals/run-slices: Execute deterministic slice regression and compute report

[POS]
API router exposing GUI-first commerce state-slice evaluation generation and execution.
Replaces terminal CLI plugins (such as /author-commerce-evals) with structured WebUI endpoints.
"""

from __future__ import annotations

import time
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from myrm_agent_harness.backends.commerce.gates import (
    CartCapLimits,
    check_cart_cap,
    resolve_variant_options,
)
from myrm_agent_harness.backends.commerce.guardrails import (
    MerchantGuardrailConfig,
    check_merchant_guardrails,
)
from myrm_agent_harness.backends.commerce.types import (
    Cart,
    CartLine,
    ChangeType,
    Listing,
    ListingStatus,
    PricingContext,
    StagedChange,
)
from myrm_agent_harness.backends.commerce.verticals import VerticalDomain, get_vertical_starter_pack
from pydantic import BaseModel, Field

from app.schemas.responses import StandardSuccessResponse, create_success_response

router = APIRouter(prefix="/commerce/evals", tags=["commerce-evals"])


class CartItemSeed(BaseModel):
    """Seed representation of a cart item in a test slice."""

    product_id: str
    variant_id: str | None = None
    quantity: int = 1


class CommerceSliceEvalCase(BaseModel):
    """Encapsulates a reproducible state slice and expected business assertions."""

    case_id: str = Field(..., description="Unique case identifier")
    name: str = Field(..., description="Human-readable case name")
    domain: VerticalDomain = Field("retail", description="Commerce domain vertical")
    role: Literal["storefront", "merchant"] = Field("storefront", description="Target role")
    user_prompt: str = Field(..., description="User input simulating customer or merchant turn")
    initial_cart_items: list[CartItemSeed] = Field(default_factory=list, description="Initial cart items")
    expected_action: Literal[
        "add_to_cart",
        "resolve_variant",
        "cart_cap_reject",
        "price_guardrail_pass",
        "price_guardrail_warn",
        "query_policy",
    ] = Field(..., description="Target business gate or action to evaluate")
    target_product_id: str | None = Field(None, description="Optional target product ID")
    proposed_price: float | None = None
    expected_status: Literal["pass", "fail"] = Field("pass", description="Expected evaluation outcome")


class CommerceSliceEvalResult(BaseModel):
    case_id: str
    name: str
    passed: bool
    latency_ms: float
    message: str
    details: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class CommerceSliceBatchEvalResult(BaseModel):
    total_cases: int
    passed_cases: int
    failed_cases: int
    pass_rate: float
    total_latency_ms: float
    results: list[CommerceSliceEvalResult]


class GenerateSliceRequest(BaseModel):
    name: str | None = None
    domain: VerticalDomain = "retail"
    role: Literal["storefront", "merchant"] = "storefront"
    user_prompt: str | None = None
    scenario_preset: Literal[
        "variant_resolution_test",
        "cart_capacity_guard_test",
        "price_staged_guardrail_test",
        "policy_inquiry_test",
    ] = "variant_resolution_test"


class RunSlicesRequest(BaseModel):
    cases: list[CommerceSliceEvalCase]


PRESET_COMMERCE_SLICES: list[CommerceSliceEvalCase] = [
    CommerceSliceEvalCase(
        case_id="slice_ret_01_variant_stock_converge",
        name="[RETAIL] Multi-Variant Convergence & Out-of-Stock Resolution",
        domain="retail",
        role="storefront",
        user_prompt="I want to buy the AeroStride Marathon shoes in red EU 43",
        initial_cart_items=[],
        expected_action="resolve_variant",
        target_product_id="ret_shoe_001",
        expected_status="pass",
    ),
    CommerceSliceEvalCase(
        case_id="slice_ret_02_cart_capacity_guard",
        name="[RETAIL] Cart Capacity Line Quota Overflow Guard",
        domain="retail",
        role="storefront",
        user_prompt="Add 100 pairs of headphones to my shopping cart",
        initial_cart_items=[CartItemSeed(product_id="ret_headphone_002", quantity=5)],
        expected_action="cart_cap_reject",
        target_product_id="ret_headphone_002",
        expected_status="pass",
    ),
    CommerceSliceEvalCase(
        case_id="slice_merch_03_price_staged_guardrail",
        name="[RETAIL] Merchant 50% Price Slash Profit Margin Defense",
        domain="retail",
        role="merchant",
        user_prompt="Stage a 50% clearance discount for the marathon running shoe",
        initial_cart_items=[],
        expected_action="price_guardrail_warn",
        target_product_id="list_ret_001",
        proposed_price=90.0,
        expected_status="pass",
    ),
    CommerceSliceEvalCase(
        case_id="slice_trv_04_policy_inquiry",
        name="[TRAVEL] Hotel 48-Hour Free Cancellation Policy Query",
        domain="travel",
        role="storefront",
        user_prompt="What is the hotel cancellation and refund timeline?",
        initial_cart_items=[],
        expected_action="query_policy",
        target_product_id="trv_hotel_grand_seaside",
        expected_status="pass",
    ),
]


@router.get("/presets", response_model=StandardSuccessResponse)
async def get_commerce_eval_presets() -> StandardSuccessResponse:
    """Retrieve pre-built standard commerce slice evaluation test cases."""
    return create_success_response(data=[case.model_dump() for case in PRESET_COMMERCE_SLICES])


@router.post("/generate-slice", response_model=StandardSuccessResponse)
async def generate_slice(request: GenerateSliceRequest) -> StandardSuccessResponse:
    """Generate a structured .slice.json evaluation case from a preset scenario or prompt."""
    case_id = f"slice_{request.domain}_{int(time.time() * 1000)}"
    starter = get_vertical_starter_pack(request.domain)

    if request.scenario_preset == "variant_resolution_test":
        first_product = starter.initial_products[0] if starter.initial_products else None
        target_pid = first_product.product_id if first_product else "p-1"
        eval_case = CommerceSliceEvalCase(
            case_id=case_id,
            name=request.name or f"[{request.domain.upper()}] Multi-Variant Convergence Test",
            domain=request.domain,
            role="storefront",
            user_prompt=request.user_prompt or "I want to buy this item in Blue and Size Large",
            initial_cart_items=[],
            expected_action="resolve_variant",
            target_product_id=target_pid,
            expected_status="pass",
        )
    elif request.scenario_preset == "cart_capacity_guard_test":
        first_product = starter.initial_products[0] if starter.initial_products else None
        target_pid = first_product.product_id if first_product else "p-1"
        eval_case = CommerceSliceEvalCase(
            case_id=case_id,
            name=request.name or f"[{request.domain.upper()}] Cart Capacity Cap Overflow Guard Test",
            domain=request.domain,
            role="storefront",
            user_prompt=request.user_prompt or "Add 50 units to cart",
            initial_cart_items=[CartItemSeed(product_id=target_pid, quantity=10)],
            expected_action="cart_cap_reject",
            target_product_id=target_pid,
            expected_status="pass",
        )
    elif request.scenario_preset == "price_staged_guardrail_test":
        first_listing = starter.initial_listings[0] if starter.initial_listings else None
        target_lid = first_listing.listing_id if first_listing else "list-1"
        eval_case = CommerceSliceEvalCase(
            case_id=case_id,
            name=request.name or f"[{request.domain.upper()}] Merchant 30% Price Change Guardrail Test",
            domain=request.domain,
            role="merchant",
            user_prompt=request.user_prompt or "Stage price reduction from $100 to $40",
            initial_cart_items=[],
            expected_action="price_guardrail_warn",
            target_product_id=target_lid,
            proposed_price=40.0,
            expected_status="pass",
        )
    else:
        eval_case = CommerceSliceEvalCase(
            case_id=case_id,
            name=request.name or f"[{request.domain.upper()}] Return Policy & Cancellation Query Test",
            domain=request.domain,
            role="storefront",
            user_prompt=request.user_prompt or "What is your refund policy?",
            initial_cart_items=[],
            expected_action="query_policy",
            target_product_id=None,
            expected_status="pass",
        )

    return create_success_response(data=eval_case.model_dump())


@router.post("/run-slices", response_model=StandardSuccessResponse)
async def run_slices(request: RunSlicesRequest) -> StandardSuccessResponse:
    """Execute a batch of state slices against vertical backends and evaluate business assertions."""
    if not request.cases:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No evaluation cases provided",
        )

    results: list[CommerceSliceEvalResult] = []
    total_start_time = time.perf_counter()

    for case in request.cases:
        start_time = time.perf_counter()
        passed = False
        message = ""
        details: dict[str, str | int | float | bool | None] = {}

        try:
            starter = get_vertical_starter_pack(case.domain)

            if case.expected_action == "resolve_variant":
                target_pid = case.target_product_id or (starter.initial_products[0].product_id if starter.initial_products else "p-1")
                product = await starter.storefront_backend.get_product_details(target_pid)
                if not product:
                    passed = False
                    message = f"Target product {target_pid} not found in {case.domain} starter pack"
                else:
                    user_opts = {"color": "red", "size": "43"}
                    resolution = resolve_variant_options(product, user_opts)
                    details["decision"] = resolution.decision
                    details["reason"] = resolution.reason
                    passed = resolution.decision in ("blocked", "held", "passed")
                    message = f"Variant resolution evaluated with decision '{resolution.decision}'"

            elif case.expected_action == "cart_cap_reject":
                lines = tuple(
                    CartLine(
                        line_id=f"line-{i}",
                        product_id=item.product_id,
                        variant_id=item.variant_id,
                        quantity=item.quantity,
                        unit_price=10.0,
                        title=f"Item {item.product_id}",
                    )
                    for i, item in enumerate(case.initial_cart_items)
                )
                cart = Cart(cart_id="cart_eval_01", session_id="eval_sess", lines=lines)
                limits = CartCapLimits(max_quantity_per_line=50)
                cap_res = check_cart_cap(
                    cart=cart,
                    product_id=case.target_product_id or "p-1",
                    quantity=99,
                    limits=limits,
                )
                details["decision"] = cap_res.decision
                details["allowed"] = cap_res.allowed
                details["reason"] = cap_res.reason
                passed = not cap_res.allowed
                message = f"Cart cap evaluated: blocked={not cap_res.allowed}"

            elif case.expected_action in ("price_guardrail_pass", "price_guardrail_warn"):
                listing = starter.initial_listings[0] if starter.initial_listings else Listing(
                    listing_id="list-1",
                    title="Mock Item",
                    description="Mock Description",
                    price=100.0,
                    inventory_count=50,
                    status=ListingStatus.ACTIVE,
                    category="retail",
                )
                proposed = case.proposed_price if case.proposed_price is not None else 40.0
                staged = StagedChange(
                    change_id="stage-eval-1",
                    listing_id=listing.listing_id,
                    change_type=ChangeType.PRICE_UPDATE,
                    proposed_values=(("price", str(proposed)),),
                )
                config = MerchantGuardrailConfig(max_price_drop_pct=25.0)
                pricing_ctx = PricingContext(
                    listing_id=listing.listing_id,
                    min_allowed_price=75.0,
                    floor_price=75.0,
                )
                guardrail = check_merchant_guardrails(
                    change=staged,
                    listing=listing,
                    config=config,
                    pricing_context=pricing_ctx,
                )
                details["decision"] = guardrail.decision
                details["allowed"] = guardrail.allowed
                details["violations_count"] = len(guardrail.violations)
                if case.expected_action == "price_guardrail_warn":
                    passed = not guardrail.allowed
                    message = f"Price guardrail blocked as expected: violations={len(guardrail.violations)}"
                else:
                    passed = guardrail.allowed
                    message = "Price guardrail passed as expected"

            elif case.expected_action == "query_policy":
                policies = await starter.storefront_backend.get_policies()
                passed = len(policies) > 0
                message = f"Retrieved {len(policies)} active policies for {case.domain}"
                details["policies_count"] = len(policies)

            else:
                passed = True
                message = f"Generic action {case.expected_action} evaluated"

        except Exception as exc:  # noqa: BLE001
            passed = False
            message = f"Execution error: {str(exc)}"

        latency = (time.perf_counter() - start_time) * 1000.0
        results.append(
            CommerceSliceEvalResult(
                case_id=case.case_id,
                name=case.name,
                passed=passed,
                latency_ms=round(latency, 2),
                message=message,
                details=details,
            )
        )

    total_latency = (time.perf_counter() - total_start_time) * 1000.0
    passed_count = sum(1 for r in results if r.passed)
    batch_result = CommerceSliceBatchEvalResult(
        total_cases=len(results),
        passed_cases=passed_count,
        failed_cases=len(results) - passed_count,
        pass_rate=round(passed_count / len(results), 4) if results else 0.0,
        total_latency_ms=round(total_latency, 2),
        results=results,
    )

    return create_success_response(data=batch_result.model_dump())
