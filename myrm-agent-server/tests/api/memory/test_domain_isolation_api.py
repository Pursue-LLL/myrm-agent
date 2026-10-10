"""Unit tests for Connection & Account Domain Isolation API (Item 156).

[INPUT]
- TestClient, FastAPI mock app, connector binding payloads, grant updates, recall & egress requests.

[OUTPUT]
- Asserts on /domain-isolation/bindings, /grants, /validate-recall, /validate-write, and /evaluate-egress endpoints.

[POS]
- Server-side test suite for Item 156 ConnectionAndAccountDomainIsolation.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.memory.domain_isolation_router import (
    router as domain_isolation_router,
)

app = FastAPI()
app.include_router(domain_isolation_router)
client = TestClient(app)


def test_set_and_get_binding_api() -> None:
    # 1. Bind work connector
    work_payload = {
        "connector_id": "feishu_corp_101",
        "domain": "work",
        "channel": "feishu",
        "account_id": "corp_user_01",
    }
    resp1 = client.post("/domain-isolation/bindings", json=work_payload)
    assert resp1.status_code == 201
    data1 = resp1.json()
    assert data1["connector_id"] == "feishu_corp_101"
    assert data1["domain"] == "work"

    # 2. Bind personal connector
    personal_payload = {
        "connector_id": "wechat_personal_102",
        "domain": "personal",
        "channel": "wechat",
        "account_id": "wx_self_02",
    }
    resp2 = client.post("/domain-isolation/bindings", json=personal_payload)
    assert resp2.status_code == 201
    data2 = resp2.json()
    assert data2["connector_id"] == "wechat_personal_102"
    assert data2["domain"] == "personal"

    # 3. Get single binding
    get_resp = client.get("/domain-isolation/bindings/wechat_personal_102")
    assert get_resp.status_code == 200
    assert get_resp.json()["domain"] == "personal"

    # 4. List bindings filtered by domain
    list_work = client.get("/domain-isolation/bindings", params={"domain": "work"})
    assert list_work.status_code == 200
    work_items = list_work.json()
    assert any(b["connector_id"] == "feishu_corp_101" for b in work_items)
    assert not any(b["connector_id"] == "wechat_personal_102" for b in work_items)


def test_list_and_update_grants_api() -> None:
    # List all grants
    list_resp = client.get("/domain-isolation/grants")
    assert list_resp.status_code == 200
    grants = list_resp.json()
    assert len(grants) == 2
    domains = {g["domain"] for g in grants}
    assert "work" in domains and "personal" in domains

    # Update personal grant to disable write
    update_resp = client.put(
        "/domain-isolation/grants/personal",
        json={"allow_write": False},
    )
    assert update_resp.status_code == 200
    updated_personal = update_resp.json()
    assert updated_personal["domain"] == "personal"
    assert updated_personal["allow_write"] is False

    # Verify work grant is untouched
    work_resp = client.get("/domain-isolation/grants/work")
    assert work_resp.status_code == 200
    assert work_resp.json()["allow_write"] is True


def test_validate_recall_api() -> None:
    # 1. Same domain recall (work -> work)
    same_resp = client.post(
        "/domain-isolation/validate-recall",
        json={
            "target_domain": "work",
            "active_domain": "work",
            "allow_cross_domain": False,
        },
    )
    assert same_resp.status_code == 200
    assert same_resp.json()["allowed"] is True
    assert same_resp.json()["is_cross_domain"] is False

    # 2. Cross domain blocked by default (work active -> personal target)
    cross_blocked = client.post(
        "/domain-isolation/validate-recall",
        json={
            "target_domain": "personal",
            "active_domain": "work",
            "allow_cross_domain": False,
        },
    )
    assert cross_blocked.status_code == 200
    res_b = cross_blocked.json()
    assert res_b["allowed"] is False
    assert res_b["is_cross_domain"] is True
    assert "跨域隔离拦截" in res_b["reason"]

    # 3. Cross domain explicitly allowed
    cross_allowed = client.post(
        "/domain-isolation/validate-recall",
        json={
            "target_domain": "personal",
            "active_domain": "work",
            "allow_cross_domain": True,
        },
    )
    assert cross_allowed.status_code == 200
    res_a = cross_allowed.json()
    assert res_a["allowed"] is True
    assert res_a["is_cross_domain"] is True


def test_validate_write_api() -> None:
    # Work domain allowed
    work_resp = client.post(
        "/domain-isolation/validate-write", json={"domain": "work"}
    )
    assert work_resp.status_code == 200
    assert work_resp.json()["allowed"] is True

    # Personal domain was disabled in test_list_and_update_grants_api
    personal_resp = client.post(
        "/domain-isolation/validate-write", json={"domain": "personal"}
    )
    assert personal_resp.status_code == 200
    assert personal_resp.json()["allowed"] is False


def test_evaluate_egress_api() -> None:
    # 1. Personal domain egress without user confirmation -> Blocked
    egress_req = {
        "content_domain": "personal",
        "target_channel": "slack_public_channel",
        "user_confirmed": False,
    }
    resp1 = client.post("/domain-isolation/evaluate-egress", json=egress_req)
    assert resp1.status_code == 200
    dec1 = resp1.json()
    assert dec1["allowed"] is False
    assert dec1["requires_user_confirmation"] is True
    assert "隐私红线触发" in dec1["reason"]

    # 2. Personal domain egress with explicit confirmation -> Allowed
    egress_req["user_confirmed"] = True
    resp2 = client.post("/domain-isolation/evaluate-egress", json=egress_req)
    assert resp2.status_code == 200
    dec2 = resp2.json()
    assert dec2["allowed"] is True
    assert dec2["requires_user_confirmation"] is False

    # 3. Work domain egress -> Allowed
    work_req = {
        "content_domain": "work",
        "target_channel": "slack_public_channel",
        "user_confirmed": False,
    }
    resp3 = client.post("/domain-isolation/evaluate-egress", json=work_req)
    assert resp3.status_code == 200
    assert resp3.json()["allowed"] is True
