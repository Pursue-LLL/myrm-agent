"""API tests for workflow template library."""

from __future__ import annotations

from fastapi.testclient import TestClient

from myrm_agent_harness.agent.dynamic_workflow.store import WorkflowEventStore
from myrm_agent_harness.agent.dynamic_workflow.template_store import compute_workflow_id

_VALID_SCRIPT = """
import myrm_tools
myrm_tools.spawn_subagent(task_id="t1", agent_type="generalPurpose", task_description="hello", readonly=True)
"""


def test_workflow_template_crud_and_from_run(client: TestClient, tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "workflow.db"
    monkeypatch.chdir(tmp_path)

    from app.services.workflow_templates import service as workflow_templates_service

    monkeypatch.setattr(
        workflow_templates_service,
        "resolve_workflow_db_path",
        lambda: db_path,
    )

    upsert_resp = client.put(
        "/api/v1/workflow-templates/demo-flow",
        json={
            "displayName": "Demo Flow",
            "scriptCode": _VALID_SCRIPT,
            "trustLatch": True,
        },
    )
    assert upsert_resp.status_code == 200
    body = upsert_resp.json()
    assert body["templateId"] == "demo-flow"
    assert body["trustLatch"] is True

    list_resp = client.get("/api/v1/workflow-templates")
    assert list_resp.status_code == 200
    templates = list_resp.json()["templates"]
    assert len(templates) == 1

    detail_resp = client.get("/api/v1/workflow-templates/demo-flow")
    assert detail_resp.status_code == 200
    assert "spawn_subagent" in detail_resp.json()["scriptCode"]

    workflow_id = compute_workflow_id("chat_save", "msg_save")
    WorkflowEventStore(db_path).save_orchestration_script(workflow_id, _VALID_SCRIPT)
    from_run_resp = client.post(
        "/api/v1/workflow-templates/from-run",
        json={
            "chatId": "chat_save",
            "messageId": "msg_save",
            "templateId": "saved-from-run",
            "displayName": "Saved From Run",
            "trustLatch": False,
        },
    )
    assert from_run_resp.status_code == 200
    assert from_run_resp.json()["templateId"] == "saved-from-run"

    delete_resp = client.delete("/api/v1/workflow-templates/demo-flow")
    assert delete_resp.status_code == 200
    assert delete_resp.json()["deleted"] is True

    missing_resp = client.get("/api/v1/workflow-templates/demo-flow")
    assert missing_resp.status_code == 404
