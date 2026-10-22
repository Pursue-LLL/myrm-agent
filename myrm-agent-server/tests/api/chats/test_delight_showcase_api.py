"""Integration and unit tests for Zero-Code Hobbyist Delight & Single-File Sandbox API.

[INPUT]
- httpx, ASGITransport
- app.api.chats.chat.delight_showcase::router

[OUTPUT]
- Pytest test cases verifying template catalog retrieval, category/query filtering, and single-file sandbox validation.

[POS]
Server-side integration test suite for Item 40 P0. Strictly under 160 lines. Zero `Any`.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport

from app.api.chats.chat.delight_showcase import router as delight_showcase_router

test_app = FastAPI()
test_app.include_router(delight_showcase_router, prefix="/api/v1/chats")


@pytest.fixture
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_list_delight_templates_all_and_filtered(async_client: httpx.AsyncClient) -> None:
    # 1. Fetch all templates
    resp_all = await async_client.get("/api/v1/chats/delight-templates")
    assert resp_all.status_code == 200
    items = resp_all.json()["data"]
    assert len(items) >= 8

    template_ids = [t["template_id"] for t in items]
    assert "tmpl_birthday_fireworks" in template_ids
    assert "tmpl_lucky_wheel" in template_ids
    assert "tmpl_pixel_pingpong" in template_ids

    # 2. Filter by category
    resp_cat = await async_client.get(
        "/api/v1/chats/delight-templates",
        params={"category": "celebration"},
    )
    assert resp_cat.status_code == 200
    cat_items = resp_cat.json()["data"]
    assert len(cat_items) >= 2
    assert all(t["category"] == "celebration" for t in cat_items)

    # 3. Fuzzy search query
    resp_q = await async_client.get(
        "/api/v1/chats/delight-templates",
        params={"q": "烟花"},
    )
    assert resp_q.status_code == 200
    q_items = resp_q.json()["data"]
    assert len(q_items) >= 1
    assert "烟花" in q_items[0]["title"] or "烟花" in q_items[0]["description"]


@pytest.mark.asyncio
async def test_get_delight_template_detail(async_client: httpx.AsyncClient) -> None:
    # Existing template
    resp = await async_client.get("/api/v1/chats/delight-templates/tmpl_birthday_fireworks")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["template_id"] == "tmpl_birthday_fireworks"
    assert "<!DOCTYPE html>" in data["html_source"]
    assert "printf" in data["html_source"]
    assert data["category"] == "celebration"

    # Non-existent template
    err_resp = await async_client.get("/api/v1/chats/delight-templates/tmpl_not_exist")
    assert err_resp.status_code == 404


@pytest.mark.asyncio
async def test_validate_delight_sandbox(async_client: httpx.AsyncClient) -> None:
    chat_id = f"chat_{uuid.uuid4().hex[:8]}"

    # Valid canvas fragment
    resp = await async_client.post(
        f"/api/v1/chats/{chat_id}/delight-sandbox/validate",
        json={
            "html_source": "<div class='h-full'><canvas id='c'></canvas></div>",
            "title": "Interactive Particle Card",
        },
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["is_valid"] is True
    assert data["has_canvas"] is True
    assert "<!DOCTYPE html>" in data["compiled_html"]
    assert "viewport" in data["compiled_html"]

    # Invalid code with relative module import
    err_resp = await async_client.post(
        f"/api/v1/chats/{chat_id}/delight-sandbox/validate",
        json={
            "html_source": "<script>import x from './relative.js';</script>",
            "title": "Invalid Card",
        },
    )
    assert err_resp.status_code == 200
    err_data = err_resp.json()["data"]
    assert err_data["is_valid"] is False
    assert len(err_data["issues"]) > 0


@pytest.mark.asyncio
async def test_create_delight_sandbox_contract(async_client: httpx.AsyncClient) -> None:
    chat_id = f"chat_{uuid.uuid4().hex[:8]}"

    resp = await async_client.post(
        f"/api/v1/chats/{chat_id}/delight-sandbox/contract",
        json={
            "title": "Birthday Demo",
            "html_source": "<html><body><h1>Happy Birthday</h1></body></html>",
        },
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["contract_id"].startswith("sc_")
    assert data["session_id"] == chat_id
    assert data["title"] == "Birthday Demo"
    assert data["is_self_contained"] is True
