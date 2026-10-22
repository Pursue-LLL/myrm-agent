"""Unit tests for Heavy MCP Payload Summarizer & Contamination Doctor API (Item 44).

[INPUT]
- app.api.agents.mcp_payload_summarizer_router.router
- app.services.agent.mcp_payload_summarizer_service.McpPayloadSummarizerService

[OUTPUT]
- Pytest test cases validating payload restructuring, token saving ratios,
  contamination audit diagnosis, and preset discovery endpoints.

[POS]
- myrm-agent/myrm-agent-server/tests/api/agents/test_mcp_payload_summarizer_api.py
"""

from __future__ import annotations

import json
from collections.abc import Generator

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.agents.mcp_payload_summarizer_router import (
    get_mcp_payload_summarizer_service,
)
from app.api.agents.mcp_payload_summarizer_router import (
    router as mcp_payload_summarizer_router,
)
from app.services.agent.mcp_payload_summarizer_service import (
    McpPayloadSummarizerService,
)


@pytest.fixture
def summarizer_service() -> McpPayloadSummarizerService:
    return McpPayloadSummarizerService()


@pytest.fixture
def client(summarizer_service: McpPayloadSummarizerService) -> Generator[TestClient, None, None]:
    app = FastAPI()
    app.include_router(mcp_payload_summarizer_router)
    app.dependency_overrides[get_mcp_payload_summarizer_service] = lambda: summarizer_service
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_summarize_payload_api(client: TestClient) -> None:
    bulky_data = {
        "title": "Notion Task Database Bulk Export",
        "total_records": 100,
        "records": [{"id": i, "content": "Detailed long task description " * 15} for i in range(50)],
        "metadata": {"export_version": "v2.1", "workspace": "engineering"},
    }
    raw_json = json.dumps(bulky_data, ensure_ascii=False)

    resp = client.post(
        "/agents/mcp-summarizer/summarize",
        json={
            "source_tool": "notion_mcp_dump",
            "raw_payload": raw_json,
            "target": {
                "required_keys": ["title", "records"],
                "max_summary_tokens": 600,
                "summarize_nested_lists_limit": 2,
            },
            "artifact_store_path": "/var/log/notion_dump.json",
        },
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["source_tool_or_mcp"] == "notion_mcp_dump"
    assert data["file_reference_path"] == "/var/log/notion_dump.json"
    assert data["raw_payload_bytes"] > 5000
    assert data["summary_bytes"] < 1500
    assert data["token_saving_ratio"] >= 0.38
    assert "Notion Task Database Bulk Export" in data["summary_text"]
    assert "title" in data["extracted_fields"]


def test_diagnose_payload_api(client: TestClient) -> None:
    # 1. Safe small payload
    resp1 = client.post(
        "/agents/mcp-summarizer/diagnose",
        json={"raw_payload": "Small response text", "is_isolated_via_subagent": False},
    )
    assert resp1.status_code == 200
    assert resp1.json()["data"]["risk_level"] == "safe"

    # 2. Suspicious medium payload
    resp2 = client.post(
        "/agents/mcp-summarizer/diagnose",
        json={"raw_payload": "x" * 8000, "is_isolated_via_subagent": False},
    )
    assert resp2.status_code == 200
    assert resp2.json()["data"]["risk_level"] == "suspicious"
    assert "mcp-data-summarizer" in resp2.json()["data"]["remediation_advice"]

    # 3. Severe contamination risk
    resp3 = client.post(
        "/agents/mcp-summarizer/diagnose",
        json={"raw_payload": "x" * 25000, "is_isolated_via_subagent": False},
    )
    assert resp3.status_code == 200
    assert resp3.json()["data"]["risk_level"] == "severe_contamination"

    # 4. Same severe payload when isolated is SAFE
    resp4 = client.post(
        "/agents/mcp-summarizer/diagnose",
        json={"raw_payload": "x" * 25000, "is_isolated_via_subagent": True},
    )
    assert resp4.status_code == 200
    assert resp4.json()["data"]["risk_level"] == "safe"


def test_get_preset_spec_api(client: TestClient) -> None:
    resp = client.get("/agents/mcp-summarizer/preset")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["name"] == "mcp-data-summarizer"
    assert "read_file" in data["tools_whitelist"]
    assert data["default_extraction_target"]["max_summary_tokens"] == 800


def test_invalid_input_error_handling(client: TestClient) -> None:
    # Empty source_tool returns 422
    bad_req1 = client.post(
        "/agents/mcp-summarizer/summarize",
        json={"source_tool": "", "raw_payload": "{}"},
    )
    assert bad_req1.status_code == 422

    # Negative max_summary_tokens returns 422
    bad_req2 = client.post(
        "/agents/mcp-summarizer/summarize",
        json={
            "source_tool": "test",
            "raw_payload": "{}",
            "target": {"max_summary_tokens": 10},
        },
    )
    assert bad_req2.status_code == 422
