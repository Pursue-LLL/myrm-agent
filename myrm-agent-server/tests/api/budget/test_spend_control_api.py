"""Unit tests for Spend Control and Soft Quota Intervention API endpoints."""

import json
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_get_spend_intervention_decision_tier1_allow():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/budget/spend-control/decision",
            params={"current_spend_usd": 5.0, "quota_limit_usd": 10.0, "session_id": "test_s1"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["tier"] == "tier_1_visibility"
        assert data["action"] == "allow"
        assert not data["isBlocked"]
        assert data["spendRatio"] == 0.5


@pytest.mark.asyncio
async def test_soft_gate_lifecycle_via_api():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. 95% spend triggers Tier 2 Soft Gate
        resp1 = await client.get(
            "/budget/spend-control/decision",
            params={"current_spend_usd": 9.5, "quota_limit_usd": 10.0, "session_id": "test_s2"},
        )
        assert resp1.status_code == 200
        d1 = resp1.json()["data"]
        assert d1["tier"] == "tier_2_soft_gate"
        assert d1["action"] == "require_confirmation"
        assert d1["isBlocked"]
        bypass_token = d1["bypassToken"]
        assert bypass_token is not None

        # 2. Confirm soft gate
        resp_conf = await client.post(
            "/budget/spend-control/confirm-soft-gate",
            json={"session_id": "test_s2", "bypass_token": bypass_token},
        )
        assert resp_conf.status_code == 200
        assert resp_conf.json()["data"]["confirmed"] is True

        # 3. Re-evaluate session: should now be unblocked
        resp2 = await client.get(
            "/budget/spend-control/decision",
            params={"current_spend_usd": 9.5, "quota_limit_usd": 10.0, "session_id": "test_s2"},
        )
        assert resp2.status_code == 200
        d2 = resp2.json()["data"]
        assert d2["tier"] == "tier_2_soft_gate"
        assert d2["action"] == "allow"
        assert not d2["isBlocked"]


@pytest.mark.asyncio
async def test_tier3_seamless_downgrade_via_api():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/budget/spend-control/decision",
            params={"current_spend_usd": 11.0, "quota_limit_usd": 10.0, "session_id": "test_s3"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["tier"] == "tier_3_auto_downgrade"
        assert data["action"] == "switch_model"
        assert not data["isBlocked"]
        assert data["downgradeModelId"] == "gpt-4o-mini"


@pytest.mark.asyncio
async def test_fleet_quota_deck_api():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Record fleet spend
        rec_resp = await client.post(
            "/budget/spend-control/record-fleet-spend",
            json={
                "dimension": "agent_profile",
                "identifier": "code_gen_agent",
                "spend_usd": 7.5,
                "quota_usd": 10.0,
                "active_sessions": 2,
            },
        )
        assert rec_resp.status_code == 200
        assert rec_resp.json()["data"]["identifier"] == "code_gen_agent"

        # Query fleet deck
        deck_resp = await client.get("/budget/spend-control/fleet-deck")
        assert deck_resp.status_code == 200
        items = deck_resp.json()["data"]["items"]
        assert any(it["identifier"] == "code_gen_agent" for it in items)
