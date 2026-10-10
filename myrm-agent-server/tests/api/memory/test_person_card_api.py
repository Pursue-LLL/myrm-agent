"""Unit tests for Person Card & Relationship Memory API (Item 155).

[INPUT]
- TestClient, FastAPI mock app, PersonCard creation payloads, merge payloads, pre-action check requests.

[OUTPUT]
- Asserts on /person-card CRUD, merge, pre-action-check, and refresh-decay endpoints.

[POS]
- Server-side test suite for Item 155 PersonCardAndRelationshipMemoryLayer.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.memory.person_card_router import router as person_card_router

app = FastAPI()
app.include_router(person_card_router)
client = TestClient(app)


def test_create_and_get_person_card_api() -> None:
    payload = {
        "person_id": "test_person_01",
        "display_name": "张三",
        "aliases": ["San Zhang", "三哥"],
        "relation_type": "friend",
        "org": "Tech Co",
        "attributes": {
            "dietary_restrictions": ["vegetarian", "no-alcohol"],
            "birthday": "1990-08-15",
            "timezone": "UTC+8",
            "preferred_contact_hours": "09:00-18:00",
            "approval_preference": "钉钉审批",
            "custom_notes": {"vip": "true"},
        },
        "commitments": ["下周二同步方案"],
        "scope": "global",
    }
    create_resp = client.post("/person-card", json=payload)
    assert create_resp.status_code == 201
    created_data = create_resp.json()
    assert created_data["person_id"] == "test_person_01"
    assert created_data["display_name"] == "张三"
    assert "vegetarian" in created_data["attributes"]["dietary_restrictions"]

    # Get by ID
    get_resp = client.get("/person-card/test_person_01")
    assert get_resp.status_code == 200
    got_data = get_resp.json()
    assert got_data["person_id"] == "test_person_01"
    assert got_data["attributes"]["timezone"] == "UTC+8"


def test_list_and_search_person_cards_api() -> None:
    # Query with alias
    search_resp = client.get("/person-card", params={"query": "三哥"})
    assert search_resp.status_code == 200
    matched = search_resp.json()
    assert len(matched) >= 1
    assert any(c["person_id"] == "test_person_01" for c in matched)

    # Query with relation filter
    filter_resp = client.get("/person-card", params={"relation_type": "friend"})
    assert filter_resp.status_code == 200
    friends = filter_resp.json()
    assert len(friends) >= 1


def test_update_and_merge_person_cards_api() -> None:
    # Create second card
    payload2 = {
        "person_id": "test_person_02",
        "display_name": "张老三",
        "aliases": ["Old San"],
        "relation_type": "friend",
        "attributes": {
            "dietary_restrictions": ["peanut-allergy"],
            "birthday": "1990-08-15",
        },
        "commitments": ["跟进报价单"],
        "scope": "global",
    }
    resp2 = client.post("/person-card", json=payload2)
    assert resp2.status_code == 201

    # Merge person_02 into person_01
    merge_payload = {
        "source_person_id": "test_person_02",
        "target_person_id": "test_person_01",
    }
    merge_resp = client.post("/person-card/merge", json=merge_payload)
    assert merge_resp.status_code == 200
    merged_data = merge_resp.json()
    assert merged_data["person_id"] == "test_person_01"
    assert "Old San" in merged_data["aliases"]
    assert "peanut-allergy" in merged_data["attributes"]["dietary_restrictions"]
    assert "vegetarian" in merged_data["attributes"]["dietary_restrictions"]
    assert "跟进报价单" in merged_data["commitments"]

    # Verify source is archived
    source_resp = client.get("/person-card/test_person_02")
    assert source_resp.status_code == 200
    assert source_resp.json()["decay_status"] == "archived"


def test_pre_action_check_api() -> None:
    req = {
        "action_type": "send_invite",
        "participant_names_or_ids": ["test_person_01", "未知李总"],
        "action_summary": "客户商务晚宴邀请",
    }
    check_resp = client.post("/person-card/pre-action-check", json=req)
    assert check_resp.status_code == 200
    res = check_resp.json()
    assert res["action_type"] == "send_invite"
    assert res["has_missing_attributes"] is True
    assert len(res["participants"]) == 2
    cue = res["prompt_cue"]
    assert "客户商务晚宴邀请" in cue
    assert "张三" in cue
    assert "未知李总" in cue
    assert "提示：部分人员缺少关键偏好/属性" in cue


def test_refresh_decay_api() -> None:
    resp = client.post("/person-card/refresh-decay", params={"weak_threshold": 0.3})
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, dict)
    assert "test_person_01" in data
