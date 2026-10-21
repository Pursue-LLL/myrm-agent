"""Integration and unit tests for Swarm Coordination, Memory Recall HUD & Owner Risk API.

[INPUT]
- httpx, ASGITransport
- app.api.chats.chat.swarm_hud::router

[OUTPUT]
- Pytest test cases verifying swarm config, subagent tasks, recalled rules toggling, and owner risk confirmations.

[POS]
Server-side integration test suite for Item 42 P0. Strictly under 160 lines. Zero `Any`.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport

from app.api.chats.chat.swarm_hud import router as swarm_hud_router

test_app = FastAPI()
test_app.include_router(swarm_hud_router, prefix="/api/v1/chats")


@pytest.fixture
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_swarm_config_endpoints(async_client: httpx.AsyncClient) -> None:
    chat_id = f"chat_{uuid.uuid4().hex[:8]}"

    # Default config
    resp = await async_client.get(f"/api/v1/chats/{chat_id}/swarm/config")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["enabled"] is False
    assert data["concurrency_quota"] == 5

    # Update config
    post_resp = await async_client.post(
        f"/api/v1/chats/{chat_id}/swarm/config",
        json={"enabled": True, "concurrency_quota": 6},
    )
    assert post_resp.status_code == 200
    updated = post_resp.json()["data"]
    assert updated["enabled"] is True
    assert updated["concurrency_quota"] == 6


@pytest.mark.asyncio
async def test_subagent_tasks_endpoints(async_client: httpx.AsyncClient) -> None:
    chat_id = f"chat_{uuid.uuid4().hex[:8]}"

    # Assign tasks
    resp = await async_client.post(
        f"/api/v1/chats/{chat_id}/swarm/tasks",
        json={
            "tasks": [
                {
                    "task_id": "task_menu_01",
                    "role_title": "Menu Architect",
                    "boundary_description": "Formulate 7-day dinner menus and allergen controls",
                    "status": "running",
                    "current_step": "Drafting signature entrees",
                    "assigned_tools": ["menu_calc"],
                },
                {
                    "task_id": "task_shift_02",
                    "role_title": "Staff Scheduler",
                    "boundary_description": "Allocate barista and kitchen shifts",
                    "status": "pending",
                },
            ]
        },
    )
    assert resp.status_code == 200
    tasks = resp.json()["data"]
    assert len(tasks) == 2
    assert tasks[0]["role_title"] == "Menu Architect"

    # Get tasks
    get_resp = await async_client.get(f"/api/v1/chats/{chat_id}/swarm/tasks")
    assert get_resp.status_code == 200
    assert len(get_resp.json()["data"]) == 2


@pytest.mark.asyncio
async def test_recalled_rules_endpoints(async_client: httpx.AsyncClient) -> None:
    chat_id = f"chat_{uuid.uuid4().hex[:8]}"

    # Record recalled rules
    post_resp = await async_client.post(
        f"/api/v1/chats/{chat_id}/swarm/recalled-rules",
        json={
            "rules": [
                {
                    "rule_id": "rule_budget_99",
                    "summary": "Monthly marketing budget strictly capped at 5000 RMB",
                    "source_turn_id": "turn_10",
                    "confidence": 0.95,
                    "is_active": True,
                    "category": "budget_limit",
                }
            ]
        },
    )
    assert post_resp.status_code == 200

    # Get rules & prompt
    get_resp = await async_client.get(f"/api/v1/chats/{chat_id}/swarm/recalled-rules")
    assert get_resp.status_code == 200
    data = get_resp.json()["data"]
    assert len(data["rules"]) == 1
    assert "Monthly marketing budget strictly capped" in data["active_prompt"]

    # Toggle active
    patch_resp = await async_client.patch(
        f"/api/v1/chats/{chat_id}/swarm/recalled-rules/rule_budget_99",
        json={"is_active": False},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["data"]["is_active"] is False


@pytest.mark.asyncio
async def test_owner_risks_endpoints(async_client: httpx.AsyncClient) -> None:
    chat_id = f"chat_{uuid.uuid4().hex[:8]}"

    # Register risks
    post_resp = await async_client.post(
        f"/api/v1/chats/{chat_id}/swarm/risks",
        json={
            "risks": [
                {
                    "risk_id": "risk_noise_01",
                    "title": "Acoustic Insulation Violation",
                    "description": "Night outdoor speakers may trigger resident noise complaints",
                    "severity": "high",
                    "external_constraint_type": "municipal_code",
                    "remediation_hint": "Restrain outdoor decibel level below 55dB after 21:00",
                }
            ]
        },
    )
    assert post_resp.status_code == 200
    risks = post_resp.json()["data"]
    assert len(risks) == 1
    assert risks[0]["is_confirmed"] is False

    # Confirm risk
    confirm_resp = await async_client.patch(
        f"/api/v1/chats/{chat_id}/swarm/risks/risk_noise_01",
        json={"is_confirmed": True, "confirmed_by": "store_owner_li"},
    )
    assert confirm_resp.status_code == 200
    data = confirm_resp.json()["data"]
    assert data["is_confirmed"] is True
    assert data["confirmed_by"] == "store_owner_li"
