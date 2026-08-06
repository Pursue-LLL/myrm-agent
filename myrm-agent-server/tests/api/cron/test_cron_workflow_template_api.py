"""Cron API guards for workflow template bindings."""

from __future__ import annotations

from typing import Generator
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from myrm_agent_harness.toolkits.cron import CronConfig, CronManager, CronScheduler
from myrm_agent_harness.toolkits.cron.stores import InMemoryCronStore

from myrm_agent_harness.agent.dynamic_workflow.template_store import WorkflowTemplateStore

_VALID_READONLY_SCRIPT = """
import myrm_tools
myrm_tools.spawn_subagent(task_id="t1", agent_type="generalPurpose", task_description="hello", readonly=True)
"""

_SCRIPT_WITH_PLACEHOLDER = """
import myrm_tools
myrm_tools.spawn_subagent(task_id="t1", agent_type="generalPurpose", task_description="{topic}", readonly=True)
"""

_NON_READONLY_SCRIPT = """
import myrm_tools
myrm_tools.spawn_subagent(task_id="t1", agent_type="generalPurpose", task_description="hello")
"""


class FakeDelivery:
    async def deliver(self, job, result):  # noqa: ANN001
        pass


@pytest.fixture
def cron_manager() -> CronManager:
    store = InMemoryCronStore()
    scheduler = CronScheduler(
        store=store,
        runners={},
        delivery=FakeDelivery(),
        config=CronConfig(),
    )
    return CronManager(store, scheduler, shell_enabled=True)


@pytest.fixture
def client(cron_manager: CronManager) -> Generator[TestClient, None, None]:
    from app.api.cron.routes import helpers, router

    test_app = FastAPI()
    test_app.include_router(router, prefix="/cron")

    with patch.object(helpers, "_get_manager", return_value=cron_manager):
        yield TestClient(test_app)


def _seed_templates(db_path) -> None:
    store = WorkflowTemplateStore(db_path)
    store.save_template(
        template_id="trusted-flow",
        display_name="Trusted Flow",
        script_code=_SCRIPT_WITH_PLACEHOLDER,
        trust_latch=True,
    )
    store.save_template(
        template_id="untrusted-flow",
        display_name="Untrusted Flow",
        script_code=_VALID_READONLY_SCRIPT,
        trust_latch=False,
    )


def test_cron_rejects_non_readonly_workflow_template(
    client: TestClient,
    tmp_path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "workflow.db"
    store = WorkflowTemplateStore(db_path)
    store.save_template(
        template_id="writable-flow",
        display_name="Writable Flow",
        script_code=_NON_READONLY_SCRIPT,
        trust_latch=True,
    )

    from app.services.workflow_templates import service as workflow_templates_service

    monkeypatch.setattr(
        workflow_templates_service,
        "resolve_workflow_db_path",
        lambda: db_path,
    )

    resp = client.post(
        "/cron",
        json={
            "name": "writable-template",
            "job_type": "agent",
            "schedule": {"kind": "interval", "interval_ms": 300_000},
            "prompt": "run audit",
            "workflow_template_id": "writable-flow",
        },
    )
    assert resp.status_code == 400
    assert "readonly" in resp.json()["detail"]


def test_cron_rejects_non_trusted_workflow_template(
    client: TestClient,
    tmp_path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "workflow.db"
    _seed_templates(db_path)

    from app.services.workflow_templates import service as workflow_templates_service

    monkeypatch.setattr(
        workflow_templates_service,
        "resolve_workflow_db_path",
        lambda: db_path,
    )

    resp = client.post(
        "/cron",
        json={
            "name": "bad-template",
            "job_type": "agent",
            "schedule": {"kind": "interval", "interval_ms": 300_000},
            "prompt": "run audit",
            "workflow_template_id": "untrusted-flow",
        },
    )
    assert resp.status_code == 400
    assert "trust_latch" in resp.json()["detail"]


def test_cron_rejects_missing_workflow_template_args(
    client: TestClient,
    tmp_path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "workflow.db"
    _seed_templates(db_path)

    from app.services.workflow_templates import service as workflow_templates_service

    monkeypatch.setattr(
        workflow_templates_service,
        "resolve_workflow_db_path",
        lambda: db_path,
    )

    resp = client.post(
        "/cron",
        json={
            "name": "missing-args",
            "job_type": "agent",
            "schedule": {"kind": "interval", "interval_ms": 300_000},
            "prompt": "run audit",
            "workflow_template_id": "trusted-flow",
        },
    )
    assert resp.status_code == 400
    assert "topic" in resp.json()["detail"]


def test_cron_accepts_trusted_workflow_template_with_args(
    client: TestClient,
    tmp_path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "workflow.db"
    _seed_templates(db_path)

    from app.services.workflow_templates import service as workflow_templates_service

    monkeypatch.setattr(
        workflow_templates_service,
        "resolve_workflow_db_path",
        lambda: db_path,
    )

    resp = client.post(
        "/cron",
        json={
            "name": "trusted-run",
            "job_type": "agent",
            "schedule": {"kind": "interval", "interval_ms": 300_000},
            "prompt": "run audit",
            "workflow_template_id": "trusted-flow",
            "workflow_template_args": {"topic": "billing"},
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["workflow_template_id"] == "trusted-flow"
    assert body["workflow_template_args"] == {"topic": "billing"}
    assert body["workflow_template_display_name"] == "Trusted Flow"


def test_cron_patch_workflow_template_args(
    client: TestClient,
    tmp_path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "workflow.db"
    _seed_templates(db_path)

    from app.services.workflow_templates import service as workflow_templates_service

    monkeypatch.setattr(
        workflow_templates_service,
        "resolve_workflow_db_path",
        lambda: db_path,
    )

    create_resp = client.post(
        "/cron",
        json={
            "name": "trusted-run",
            "job_type": "agent",
            "schedule": {"kind": "interval", "interval_ms": 300_000},
            "prompt": "run audit",
            "workflow_template_id": "trusted-flow",
            "workflow_template_args": {"topic": "billing"},
        },
    )
    assert create_resp.status_code == 201
    job_id = create_resp.json()["id"]

    patch_resp = client.patch(
        f"/cron/{job_id}",
        json={"workflow_template_args": {"topic": "finance"}},
    )
    assert patch_resp.status_code == 200
    body = patch_resp.json()
    assert body["workflow_template_args"] == {"topic": "finance"}
    assert body["workflow_template_display_name"] == "Trusted Flow"


def test_cron_display_name_null_when_template_deleted(
    client: TestClient,
    tmp_path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "workflow.db"
    _seed_templates(db_path)

    from app.services.workflow_templates import service as workflow_templates_service

    monkeypatch.setattr(
        workflow_templates_service,
        "resolve_workflow_db_path",
        lambda: db_path,
    )

    create_resp = client.post(
        "/cron",
        json={
            "name": "orphan-after-delete",
            "job_type": "agent",
            "schedule": {"kind": "interval", "interval_ms": 300_000},
            "prompt": "run audit",
            "workflow_template_id": "trusted-flow",
            "workflow_template_args": {"topic": "billing"},
        },
    )
    assert create_resp.status_code == 201
    job_id = create_resp.json()["id"]

    WorkflowTemplateStore(db_path).delete_template("trusted-flow")

    get_resp = client.get(f"/cron/{job_id}")
    assert get_resp.status_code == 200
    body = get_resp.json()
    assert body["workflow_template_id"] == "trusted-flow"
    assert body["workflow_template_display_name"] is None


def test_cron_display_name_null_when_template_untrusted(
    client: TestClient,
    tmp_path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "workflow.db"
    _seed_templates(db_path)

    from app.services.workflow_templates import service as workflow_templates_service

    monkeypatch.setattr(
        workflow_templates_service,
        "resolve_workflow_db_path",
        lambda: db_path,
    )

    create_resp = client.post(
        "/cron",
        json={
            "name": "orphan-after-untrust",
            "job_type": "agent",
            "schedule": {"kind": "interval", "interval_ms": 300_000},
            "prompt": "run audit",
            "workflow_template_id": "trusted-flow",
            "workflow_template_args": {"topic": "billing"},
        },
    )
    assert create_resp.status_code == 201
    job_id = create_resp.json()["id"]

    store = WorkflowTemplateStore(db_path)
    record = store.get_template("trusted-flow")
    assert record is not None
    store.save_template(
        template_id="trusted-flow",
        display_name=record.display_name,
        script_code=record.script_code,
        trust_latch=False,
    )

    get_resp = client.get(f"/cron/{job_id}")
    assert get_resp.status_code == 200
    body = get_resp.json()
    assert body["workflow_template_id"] == "trusted-flow"
    assert body["workflow_template_display_name"] is None
