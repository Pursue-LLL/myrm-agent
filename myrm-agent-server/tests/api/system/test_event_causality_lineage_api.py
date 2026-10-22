"""
[INPUT]:
- httpx, ASGITransport
- app.api.system.event_causality_lineage_api::router

[OUTPUT]:
- Pytest verification for event-driven causality lineage tracking and reverse file attribution REST endpoints.

[POS]:
tests/api/system/test_event_causality_lineage_api.py — 事件驱动因果溯源与动作归因图谱 API 单元测试。
"""

from collections.abc import AsyncGenerator

from fastapi import FastAPI
import httpx
from httpx import ASGITransport
import pytest

from app.api.system.event_causality_lineage_api import router as causality_router

test_app = FastAPI()
test_app.include_router(causality_router, prefix="/api/v1/system")


@pytest.fixture
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_event_causality_lineage_api_flow(async_client: httpx.AsyncClient) -> None:
    # 1. Reset tracker to clean state
    reset_resp = await async_client.post("/api/v1/system/event-causality/reset")
    assert reset_resp.status_code == 200
    assert reset_resp.json() == {"ok": True}

    # 2. Initially empty lineages
    init_list = await async_client.get("/api/v1/system/event-causality/lineages")
    assert init_list.status_code == 200
    assert len(init_list.json()) == 0

    # 3. Record an end-to-end causality DAG
    payload = {
        "causality_trace_id": "trace-gh-404-fix",
        "session_id": "sess-sec-99",
        "trigger": {
            "event_id": "gh-evt-1001",
            "source_type": "github_webhook",
            "event_name": "issues.labeled",
            "payload_summary": "Bug label added to issue #404: NullPointerException in auth service",
            "received_at_ms": 1700000000000,
        },
        "rule": {
            "rule_id": "rule-auto-patch",
            "rule_name": "Auto Issue Triage & Self-Healing",
            "matched_condition": "event.label == 'bug' && target.service == 'auth'",
        },
        "agent_role": "Security & Reliability Lead",
        "actions": [
            {
                "action_id": "act-1",
                "agent_role": "Codebase Investigator",
                "decision_rationale": "Analyze stack trace and locate missing null check in auth token parser",
                "tool_name": "search_codebase",
                "input_summary": "pattern='AuthTokenParser.parse'",
                "duration_ms": 420.5,
                "tokens_consumed": 1250,
                "timestamp_ms": 1700000001000,
            },
            {
                "action_id": "act-2",
                "agent_role": "Patch Engineer",
                "decision_rationale": "Inject safe guard null check before decrypting token payload",
                "tool_name": "patch_file",
                "input_summary": "target='auth/parser.py'",
                "duration_ms": 280.0,
                "tokens_consumed": 800,
                "timestamp_ms": 1700000002000,
            },
        ],
        "artifacts": [
            {
                "file_path": "auth/parser.py",
                "change_type": "modified",
                "diff_summary": "+ if not raw_token: return None",
                "commit_sha": "a1b2c3d4e5f6",
                "timestamp_ms": 1700000002500,
            },
            {
                "file_path": "tests/test_parser.py",
                "change_type": "created",
                "diff_summary": "+ def test_empty_token_returns_none(): ...",
                "commit_sha": "a1b2c3d4e5f6",
                "timestamp_ms": 1700000002800,
            },
        ],
    }

    record_resp = await async_client.post("/api/v1/system/event-causality/record", json=payload)
    assert record_resp.status_code == 200
    rec_data = record_resp.json()
    assert rec_data["causality_trace_id"] == "trace-gh-404-fix"
    assert rec_data["total_tokens"] == 2050
    assert rec_data["total_duration_ms"] == pytest.approx(700.5)
    assert len(rec_data["actions"]) == 2
    assert len(rec_data["artifacts"]) == 2

    # 4. Query DAG by trace ID
    get_resp = await async_client.get("/api/v1/system/event-causality/lineage/trace-gh-404-fix")
    assert get_resp.status_code == 200
    get_data = get_resp.json()
    assert get_data["trigger"]["event_name"] == "issues.labeled"
    assert get_data["rule"]["rule_name"] == "Auto Issue Triage & Self-Healing"

    # 5. Query non-existent trace returns 404
    not_found_resp = await async_client.get("/api/v1/system/event-causality/lineage/unknown-trace")
    assert not_found_resp.status_code == 404

    # 6. List lineages with filter
    list_resp = await async_client.get(
        "/api/v1/system/event-causality/lineages",
        params={"source_type": "github_webhook"},
    )
    assert list_resp.status_code == 200
    items = list_resp.json()
    assert len(items) == 1
    assert items[0]["causality_trace_id"] == "trace-gh-404-fix"

    # 7. Reverse lookup file change attribution
    rev_resp = await async_client.get(
        "/api/v1/system/event-causality/reverse-lookup",
        params={"file_path": "auth/parser.py"},
    )
    assert rev_resp.status_code == 200
    rev_data = rev_resp.json()
    assert len(rev_data) == 1
    attr = rev_data[0]
    assert attr["file_path"] == "auth/parser.py"
    assert attr["causality_trace_id"] == "trace-gh-404-fix"
    assert attr["trigger_event_id"] == "gh-evt-1001"
    assert attr["source_type"] == "github_webhook"
    assert "Inject safe guard null check" in attr["rationale"]

    # 8. Reverse lookup for untouched file returns empty list
    empty_rev = await async_client.get(
        "/api/v1/system/event-causality/reverse-lookup",
        params={"file_path": "non_existent/file.py"},
    )
    assert empty_rev.status_code == 200
    assert len(empty_rev.json()) == 0
