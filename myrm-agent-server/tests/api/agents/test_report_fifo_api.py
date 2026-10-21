"""Unit tests for Subagent report delivery wakeup and ordered settlement FIFO API endpoints.

[INPUT]
- app.api.agents.report_fifo_router.router
- app.services.agent.report_fifo_service.ReportFifoService

[OUTPUT]
- Pytest test cases verifying multi-instance registration, report submission with next-step wakeup flag, ordered report-before-settlement FIFO, step-boundary queue drain, and queue status overview.

[POS]
myrm-agent/myrm-agent-server/tests/api/agents/test_report_fifo_api.py
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.agents.report_fifo_router import (
    get_report_fifo_service,
)
from app.api.agents.report_fifo_router import (
    router as report_fifo_router,
)
from app.services.agent.report_fifo_service import ReportFifoService


@pytest.fixture
def mock_fifo_service() -> ReportFifoService:
    return ReportFifoService()


@pytest.fixture
def fifo_client(
    mock_fifo_service: ReportFifoService,
) -> Generator[TestClient, None, None]:
    app = FastAPI()
    app.include_router(report_fifo_router)
    app.dependency_overrides[get_report_fifo_service] = lambda: mock_fifo_service
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_register_instances_api(fifo_client: TestClient) -> None:
    chat_id = "chat_test_fifo_01"
    payload = {
        "instances": [
            {
                "instance_name": "worker-reviewer",
                "role": "code_reviewer",
                "model_name": "claude-3-7-sonnet",
                "permission_mode": "approve-for-me",
                "report_delivery": "next-step",
                "tools_allowed": ["git_diff", "linter"],
            },
            {
                "instance_name": "worker-runner",
                "role": "test_runner",
                "model_name": "gpt-4o",
                "permission_mode": "never",
                "report_delivery": "quiet",
                "tools_allowed": ["pytest"],
            },
        ]
    }

    resp = fifo_client.post(f"/chats/{chat_id}/report-fifo/register", json=payload)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) == 2
    assert data[0]["instance_name"] == "worker-reviewer"
    assert data[1]["report_delivery"] == "quiet"


def test_report_before_settlement_fifo_api(fifo_client: TestClient) -> None:
    chat_id = "chat_test_fifo_02"

    # Register worker
    fifo_client.post(
        f"/chats/{chat_id}/report-fifo/register",
        json={
            "instances": [
                {
                    "instance_name": "subagent-alpha",
                    "role": "implementer",
                    "report_delivery": "next-step",
                }
            ]
        },
    )

    # 1. Submit progress report (next-step -> wakes_parent=True)
    report_payload = {
        "instance_name": "subagent-alpha",
        "task_id": "task_sub_101",
        "summary": "Completed parser implementation",
        "content": "Added AST parser with 100% unit tests.",
    }
    resp_rep = fifo_client.post(f"/chats/{chat_id}/report-fifo/report", json=report_payload)
    assert resp_rep.status_code == 200
    rep_data = resp_rep.json()["data"]
    assert rep_data["item_type"] == "report"
    assert rep_data["wakes_parent"] is True
    assert rep_data["report_payload"]["summary"] == "Completed parser implementation"

    # 2. Submit settlement notice
    settlement_payload = {
        "instance_name": "subagent-alpha",
        "task_id": "task_sub_101",
        "exit_code": 0,
        "status": "completed",
        "summary": "Subagent alpha finished successfully",
    }
    resp_set = fifo_client.post(f"/chats/{chat_id}/report-fifo/settlement", json=settlement_payload)
    assert resp_set.status_code == 200
    set_data = resp_set.json()["data"]
    assert set_data["item_type"] == "settlement"
    assert set_data["sequence_id"] > rep_data["sequence_id"]

    # 3. Drain and verify strict Report-before-Settlement order
    resp_drain = fifo_client.post(f"/chats/{chat_id}/report-fifo/drain", json={"max_items": 10})
    assert resp_drain.status_code == 200
    drain_data = resp_drain.json()["data"]
    items = drain_data["drained_items"]
    assert len(items) == 2
    assert items[0]["item_type"] == "report"
    assert items[1]["item_type"] == "settlement"
    assert drain_data["remaining_count"] == 0


def test_quiet_delivery_and_status_api(fifo_client: TestClient) -> None:
    chat_id = "chat_test_fifo_03"

    # 1. Submit report with quiet mode -> wakes_parent=False
    report_payload = {
        "instance_name": "subagent-beta",
        "task_id": "task_sub_102",
        "summary": "Quiet background heartbeat",
        "delivery_mode": "quiet",
    }
    resp_rep = fifo_client.post(f"/chats/{chat_id}/report-fifo/report", json=report_payload)
    assert resp_rep.status_code == 200
    rep_data = resp_rep.json()["data"]
    assert rep_data["wakes_parent"] is False

    # 2. Inspect queue status
    resp_status = fifo_client.get(f"/chats/{chat_id}/report-fifo/status")
    assert resp_status.status_code == 200
    status_data = resp_status.json()["data"]
    assert status_data["pending_count"] == 1
    assert len(status_data["items"]) == 1
    assert status_data["items"][0]["item_type"] == "report"


def test_cleanup_report_fifo_api(fifo_client: TestClient) -> None:
    chat_id = "chat_test_fifo_04"

    # Enqueue a report
    fifo_client.post(
        f"/chats/{chat_id}/report-fifo/report",
        json={
            "instance_name": "worker-ephemeral",
            "task_id": "task_sub_999",
            "summary": "Temporary work",
        },
    )

    # Verify pending
    status_before = fifo_client.get(f"/chats/{chat_id}/report-fifo/status").json()["data"]
    assert status_before["pending_count"] == 1

    # Cleanup session
    resp_del = fifo_client.delete(f"/chats/{chat_id}/report-fifo")
    assert resp_del.status_code == 200
    assert resp_del.json()["data"]["cleaned"] is True

    # Status after cleanup should be fresh empty
    status_after = fifo_client.get(f"/chats/{chat_id}/report-fifo/status").json()["data"]
    assert status_after["pending_count"] == 0


def test_critical_urgent_interrupt_and_summary_rollup_api(fifo_client: TestClient) -> None:
    chat_id = "chat_test_fifo_05"

    # 1. Submit normal report
    fifo_client.post(
        f"/chats/{chat_id}/report-fifo/report",
        json={
            "instance_name": "worker_normal",
            "task_id": "task_norm_1",
            "summary": "Completed lint check",
            "severity": "normal",
        },
    )

    # 2. Submit critical report
    resp_crit = fifo_client.post(
        f"/chats/{chat_id}/report-fifo/report",
        json={
            "instance_name": "worker_alert",
            "task_id": "task_crit_99",
            "summary": "External gateway connection timed out",
            "severity": "critical",
        },
    )
    assert resp_crit.status_code == 200
    crit_data = resp_crit.json()["data"]
    assert crit_data["urgent_interrupt"] is True
    assert crit_data["wakes_parent"] is True
    assert crit_data["report_payload"]["severity"] == "critical"

    # 3. Drain and verify urgent_interrupt and summary_rollup
    resp_drain = fifo_client.post(f"/chats/{chat_id}/report-fifo/drain", json={"max_items": 10})
    assert resp_drain.status_code == 200
    drain_data = resp_drain.json()["data"]
    assert drain_data["urgent_interrupt"] is True
    assert "[CRITICAL] Report: External gateway connection timed out" in drain_data["summary_rollup"]
    assert "Report: Completed lint check" in drain_data["summary_rollup"]

    # Critical report was prepended to head
    items = drain_data["drained_items"]
    assert len(items) == 2
    assert items[0]["task_id"] == "task_crit_99"
    assert items[0]["urgent_interrupt"] is True
    assert items[1]["task_id"] == "task_norm_1"

