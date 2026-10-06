"""
[POS] tests/api/memory/test_memory_dual_track_api.py
[INPUT] fastapi.FastAPI, starlette.testclient.TestClient, app.api.memory.dual_track_router, app.services.memory.memory_dual_track_service
[OUTPUT] test_extract_procedural_track_and_query_rules_api, test_extract_fact_track_and_query_facts_api, test_extract_dual_track_simultaneous_api, test_extract_no_signal_anti_silent_drop_transparent_reporting_api

Unit test suite for dual-track fact/procedural extraction gateway and anti-silent-drop reporting API endpoints.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.memory.dual_track_router import router as memory_dual_track_router
from app.services.memory.memory_dual_track_service import (
    MemoryDualTrackService,
    get_memory_dual_track_service,
)


@pytest.fixture
def dual_track_test_client() -> Generator[tuple[TestClient, MemoryDualTrackService], None, None]:
    """Provide isolated TestClient mounting dual-track memory router with a clean service instance."""
    service = MemoryDualTrackService()

    test_app = FastAPI()
    test_app.include_router(memory_dual_track_router, prefix="/api/memory")
    test_app.dependency_overrides[get_memory_dual_track_service] = lambda: service

    with TestClient(test_app) as client:
        yield client, service


def test_extract_procedural_track_and_query_rules_api(
    dual_track_test_client: tuple[TestClient, MemoryDualTrackService],
) -> None:
    """Verify POST /api/memory/dual-track/extract identifies procedural operational instruction and persists rules."""
    client, _ = dual_track_test_client

    payload = {
        "text": "以后写Go代码记得加上context，遇到错误必须用fmt.Errorf包装并打印堆栈",
        "domain": "golang",
        "auto_persist": True,
    }

    res = client.post("/api/memory/dual-track/extract", json=payload)
    assert res.status_code == 200
    data = res.json()

    assert data["destiny"] == "stored_procedural"
    assert data["track"] == "procedural_rule"
    assert len(data["extracted_rules"]) >= 1
    assert len(data["extracted_facts"]) == 0
    assert data["discard_reason"] == ""

    rule_id = data["extracted_rules"][0]["rule_id"]

    # Verify querying all rules
    rules_res = client.get("/api/memory/dual-track/rules")
    assert rules_res.status_code == 200
    rules_data = rules_res.json()
    assert rules_data["total"] >= 1
    assert any(r["rule_id"] == rule_id for r in rules_data["rules"])

    # Verify single rule lookup
    single_rule_res = client.get(f"/api/memory/dual-track/rules/{rule_id}")
    assert single_rule_res.status_code == 200
    assert single_rule_res.json()["rule_id"] == rule_id


def test_extract_fact_track_and_query_facts_api(
    dual_track_test_client: tuple[TestClient, MemoryDualTrackService],
) -> None:
    """Verify POST /api/memory/dual-track/extract classifies declarative user fact and persists it."""
    client, _ = dual_track_test_client

    payload = {
        "text": "我的首选编程语言是Python和Rust，工作时区固定为Asia/Shanghai",
        "domain": "general",
        "auto_persist": True,
    }

    res = client.post("/api/memory/dual-track/extract", json=payload)
    assert res.status_code == 200
    data = res.json()

    assert data["destiny"] == "stored_semantic"
    assert data["track"] == "fact_profile"
    assert len(data["extracted_facts"]) >= 1
    assert len(data["extracted_rules"]) == 0

    # Verify querying persisted facts
    facts_res = client.get("/api/memory/dual-track/facts")
    assert facts_res.status_code == 200
    facts_data = facts_res.json()
    assert facts_data["total"] >= 1


def test_extract_dual_track_simultaneous_api(
    dual_track_test_client: tuple[TestClient, MemoryDualTrackService],
) -> None:
    """Verify extraction handles input containing both declarative state and actionable procedural commands."""
    client, _ = dual_track_test_client

    payload = {
        "text": "我负责全天候运维核心支付网关。以后只要触发CPU熔断告警，必须立即发送企微告警通知值班群",
        "domain": "devops",
        "auto_persist": True,
    }

    res = client.post("/api/memory/dual-track/extract", json=payload)
    assert res.status_code == 200
    data = res.json()

    assert data["destiny"] == "stored_dual"
    assert data["track"] == "dual_track"
    assert len(data["extracted_facts"]) >= 1
    assert len(data["extracted_rules"]) >= 1


def test_extract_no_signal_anti_silent_drop_transparent_reporting_api(
    dual_track_test_client: tuple[TestClient, MemoryDualTrackService],
) -> None:
    """Verify anti-silent-drop gateway provides transparent reason when discarding chitchat, preventing silent loss."""
    client, _ = dual_track_test_client

    payload = {
        "text": "好的收到，非常感谢你的热心帮助！",
        "domain": "general",
        "auto_persist": True,
    }

    res = client.post("/api/memory/dual-track/extract", json=payload)
    assert res.status_code == 200
    data = res.json()

    assert data["destiny"] == "discarded_no_signal"
    assert data["track"] == "no_signal"
    assert len(data["extracted_facts"]) == 0
    assert len(data["extracted_rules"]) == 0
    assert len(data["discard_reason"]) > 0
    assert "No actionable" in data["discard_reason"] or "too short" in data["discard_reason"]

    # Verify 404 for non-existent rule
    missing_res = client.get("/api/memory/dual-track/rules/rule_does_not_exist_404")
    assert missing_res.status_code == 404
