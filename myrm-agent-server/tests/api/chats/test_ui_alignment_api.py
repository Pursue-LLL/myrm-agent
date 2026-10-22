"""Integration and unit tests for UI Design Visual Alignment API.

[INPUT]
- httpx, ASGITransport
- app.api.chats.chat.ui_alignment::router

[OUTPUT]
- Pytest test cases verifying variant registration, annotation attachment, and visual contract finalization.

[POS]
Server-side integration test suite for Item 39 P0. Strictly under 160 lines. Zero `Any`.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport

from app.api.chats.chat.ui_alignment import router as ui_alignment_router

test_app = FastAPI()
test_app.include_router(ui_alignment_router, prefix="/api/v1/chats")


@pytest.fixture
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_register_and_list_variants(async_client: httpx.AsyncClient) -> None:
    chat_id = f"chat_{uuid.uuid4().hex[:8]}"

    # Initially empty
    list_resp = await async_client.get(f"/api/v1/chats/{chat_id}/ui-variants")
    assert list_resp.status_code == 200
    assert list_resp.json()["data"] == []

    # Register variant
    reg_resp = await async_client.post(
        f"/api/v1/chats/{chat_id}/ui-variants",
        json={
            "title": "Bento Grid Dashboard",
            "style_theme": "modern_bento",
            "html_content": "<div class='grid grid-cols-3 gap-4'><card>Widget</card></div>",
            "css_tokens": {"--accent": "#3b82f6", "--bg": "#0f172a"},
            "description": "Information dense bento layout",
            "variant_id": "var_bento_01",
        },
    )
    assert reg_resp.status_code == 200
    data = reg_resp.json()["data"]
    assert data["variant_id"] == "var_bento_01"
    assert data["style_theme"] == "modern_bento"

    # Verify listing
    list_resp2 = await async_client.get(f"/api/v1/chats/{chat_id}/ui-variants")
    assert list_resp2.status_code == 200
    items = list_resp2.json()["data"]
    assert len(items) == 1
    assert items[0]["variant_id"] == "var_bento_01"


@pytest.mark.asyncio
async def test_add_and_list_visual_annotations(async_client: httpx.AsyncClient) -> None:
    chat_id = f"chat_{uuid.uuid4().hex[:8]}"

    # Register variant first
    await async_client.post(
        f"/api/v1/chats/{chat_id}/ui-variants",
        json={
            "title": "Minimal Dark",
            "style_theme": "minimal_dark",
            "html_content": "<main><section>Content</section></main>",
            "variant_id": "var_dark_01",
        },
    )

    # Add canvas annotation
    anno_resp = await async_client.post(
        f"/api/v1/chats/{chat_id}/ui-variants/var_dark_01/annotations",
        json={
            "x": 20.0,
            "y": 15.0,
            "width": 60.0,
            "height": 30.0,
            "comment": "Hero title typography is too heavy, reduce to font-medium",
            "label": "typography",
        },
    )
    assert anno_resp.status_code == 200
    anno_data = anno_resp.json()["data"]
    assert anno_data["variant_id"] == "var_dark_01"
    assert anno_data["x"] == 20.0
    assert "typography" in anno_data["label"]

    # List annotations
    list_resp = await async_client.get(
        f"/api/v1/chats/{chat_id}/ui-variants/var_dark_01/annotations"
    )
    assert list_resp.status_code == 200
    annotations = list_resp.json()["data"]
    assert len(annotations) == 1
    assert annotations[0]["annotation_id"] == anno_data["annotation_id"]


@pytest.mark.asyncio
async def test_finalize_visual_contract_lifecycle(async_client: httpx.AsyncClient) -> None:
    chat_id = f"chat_{uuid.uuid4().hex[:8]}"

    # 1. Initially contract is None
    init_contract = await async_client.get(f"/api/v1/chats/{chat_id}/ui-variants/contract")
    assert init_contract.status_code == 200
    assert init_contract.json()["data"] is None

    # 2. Register variant
    await async_client.post(
        f"/api/v1/chats/{chat_id}/ui-variants",
        json={
            "title": "Neo Brutalism Layout",
            "style_theme": "neo_brutalism",
            "html_content": "<button class='border-4 border-black shadow-brutal'>Action</button>",
            "css_tokens": {"--border-width": "4px", "--shadow": "4px 4px 0px #000"},
            "variant_id": "var_brutal_01",
        },
    )

    # 3. Add annotation
    await async_client.post(
        f"/api/v1/chats/{chat_id}/ui-variants/var_brutal_01/annotations",
        json={
            "x": 10.0,
            "y": 10.0,
            "width": 80.0,
            "height": 20.0,
            "comment": "Ensure button focus-visible outline conforms to a11y standards",
            "label": "accessibility",
        },
    )

    # 4. Finalize contract
    fin_resp = await async_client.post(
        f"/api/v1/chats/{chat_id}/ui-variants/finalize",
        json={"approved_variant_id": "var_brutal_01"},
    )
    assert fin_resp.status_code == 200
    contract_data = fin_resp.json()["data"]
    assert contract_data["approved_variant_id"] == "var_brutal_01"
    assert contract_data["style_theme"] == "neo_brutalism"
    assert contract_data["annotations_count"] == 1
    assert "VISUAL DESIGN CONTRACT ENFORCEMENT" in contract_data["enforcement_prompt"]

    # 5. Fetch finalized contract
    contract_fetch = await async_client.get(f"/api/v1/chats/{chat_id}/ui-variants/contract")
    assert contract_fetch.status_code == 200
    assert contract_fetch.json()["data"]["contract_id"] == contract_data["contract_id"]


@pytest.mark.asyncio
async def test_error_handling_variant_not_found(async_client: httpx.AsyncClient) -> None:
    chat_id = f"chat_{uuid.uuid4().hex[:8]}"

    # Add annotation on non-existent variant
    err_anno = await async_client.post(
        f"/api/v1/chats/{chat_id}/ui-variants/missing_id/annotations",
        json={
            "x": 0.0,
            "y": 0.0,
            "width": 10.0,
            "height": 10.0,
            "comment": "invalid",
        },
    )
    assert err_anno.status_code == 404

    # Finalize non-existent variant
    err_fin = await async_client.post(
        f"/api/v1/chats/{chat_id}/ui-variants/finalize",
        json={"approved_variant_id": "missing_id"},
    )
    assert err_fin.status_code == 404
