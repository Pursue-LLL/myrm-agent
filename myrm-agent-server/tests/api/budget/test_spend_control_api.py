"""Unit tests for Spend Control and Soft Quota Intervention API handlers."""

import json

import pytest

from app.api.budget.spend_control_router import (
    FleetSpendRecordRequest,
    SoftGateConfirmRequest,
    confirm_soft_gate,
    get_fleet_quota_deck,
    get_spend_intervention_decision,
    record_fleet_spend,
)


@pytest.mark.asyncio
async def test_get_spend_intervention_decision_tier1_allow():
    resp = await get_spend_intervention_decision(
        current_spend_usd=5.0,
        quota_limit_usd=10.0,
        session_id="test_s1",
    )
    assert resp.status_code == 200
    body = json.loads(resp.body)
    data = body["data"]
    assert data["tier"] == "tier_1_visibility"
    assert data["action"] == "allow"
    assert not data["isBlocked"]
    assert data["spendRatio"] == 0.5


@pytest.mark.asyncio
async def test_soft_gate_lifecycle_via_api():
    # 1. 95% spend triggers Tier 2 Soft Gate
    resp1 = await get_spend_intervention_decision(
        current_spend_usd=9.5,
        quota_limit_usd=10.0,
        session_id="test_s2",
    )
    assert resp1.status_code == 200
    d1 = json.loads(resp1.body)["data"]
    assert d1["tier"] == "tier_2_soft_gate"
    assert d1["action"] == "require_confirmation"
    assert d1["isBlocked"]
    bypass_token = d1["bypassToken"]
    assert bypass_token is not None

    # 2. Confirm soft gate
    conf_req = SoftGateConfirmRequest(session_id="test_s2", bypass_token=bypass_token)
    resp_conf = await confirm_soft_gate(conf_req)
    assert resp_conf.status_code == 200
    assert json.loads(resp_conf.body)["data"]["confirmed"] is True

    # 3. Re-evaluate session: should now be unblocked
    resp2 = await get_spend_intervention_decision(
        current_spend_usd=9.5,
        quota_limit_usd=10.0,
        session_id="test_s2",
    )
    assert resp2.status_code == 200
    d2 = json.loads(resp2.body)["data"]
    assert d2["tier"] == "tier_2_soft_gate"
    assert d2["action"] == "allow"
    assert not d2["isBlocked"]


@pytest.mark.asyncio
async def test_tier3_seamless_downgrade_via_api():
    resp = await get_spend_intervention_decision(
        current_spend_usd=11.0,
        quota_limit_usd=10.0,
        session_id="test_s3",
    )
    assert resp.status_code == 200
    data = json.loads(resp.body)["data"]
    assert data["tier"] == "tier_3_auto_downgrade"
    assert data["action"] == "switch_model"
    assert not data["isBlocked"]
    assert data["downgradeModelId"] == "gpt-4o-mini"


@pytest.mark.asyncio
async def test_fleet_quota_deck_api():
    # Record fleet spend
    rec_req = FleetSpendRecordRequest(
        dimension="agent_profile",
        identifier="code_gen_agent",
        spend_usd=7.5,
        quota_usd=10.0,
        active_sessions=2,
    )
    rec_resp = await record_fleet_spend(rec_req)
    assert rec_resp.status_code == 200
    assert json.loads(rec_resp.body)["data"]["identifier"] == "code_gen_agent"

    # Query fleet deck
    deck_resp = await get_fleet_quota_deck()
    assert deck_resp.status_code == 200
    items = json.loads(deck_resp.body)["data"]["items"]
    assert any(it["identifier"] == "code_gen_agent" for it in items)
