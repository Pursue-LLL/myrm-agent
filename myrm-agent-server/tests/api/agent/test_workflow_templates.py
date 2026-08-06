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
    detail_body = detail_resp.json()
    assert "spawn_subagent" in detail_body["scriptCode"]
    assert detail_body["boundCronCount"] == 0

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


def test_workflow_template_detail_reports_bound_cron_count(
    client: TestClient,
    tmp_path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "workflow.db"
    monkeypatch.chdir(tmp_path)

    from app.services.workflow_templates import service as workflow_templates_service

    monkeypatch.setattr(
        workflow_templates_service,
        "resolve_workflow_db_path",
        lambda: db_path,
    )

    upsert_resp = client.put(
        "/api/v1/workflow-templates/bound-flow",
        json={
            "displayName": "Bound Flow",
            "scriptCode": _VALID_SCRIPT,
            "trustLatch": True,
        },
    )
    assert upsert_resp.status_code == 200

    from myrm_agent_harness.toolkits.cron import CronConfig, CronManager, CronScheduler
    from myrm_agent_harness.toolkits.cron.stores import InMemoryCronStore
    from myrm_agent_harness.toolkits.cron.types import CronJob, JobStatus, JobType, Schedule, ScheduleKind

    class FakeDelivery:
        async def deliver(self, job, result):  # noqa: ANN001
            pass

    store = InMemoryCronStore()
    scheduler = CronScheduler(
        store=store,
        runners={},
        delivery=FakeDelivery(),
        config=CronConfig(),
    )
    cron_manager = CronManager(store, scheduler, shell_enabled=True)

    async def _seed_bound_job() -> None:
        await store.save_job(
            CronJob(
                id="cron-bound-1",
                user_id="default",
                name="bound job",
                job_type=JobType.AGENT,
                status=JobStatus.ACTIVE,
                schedule=Schedule(kind=ScheduleKind.INTERVAL, interval_ms=300_000),
                prompt="run",
                workflow_template_id="bound-flow",
            )
        )

    import asyncio

    asyncio.run(_seed_bound_job())

    from app.core.cron.adapters import setup as cron_setup

    monkeypatch.setattr(cron_setup, "get_cron_manager", lambda: cron_manager)

    detail_resp = client.get("/api/v1/workflow-templates/bound-flow")
    assert detail_resp.status_code == 200
    assert detail_resp.json()["boundCronCount"] == 1
