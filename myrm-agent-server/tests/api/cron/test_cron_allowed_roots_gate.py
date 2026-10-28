"""A cron job's allowed roots go through the workspace path gate when they are stored.

An allowed root widens what the job's agent may write, so one that is, or contains, a protected location is refused.
A root may also name a single file or a folder that does not exist yet, so only the checks that protect locations apply.
"""

from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import Response
from myrm_agent_harness.toolkits.cron import CronConfig, CronManager, CronScheduler
from myrm_agent_harness.toolkits.cron.stores import InMemoryCronStore

from app.api.cron.routes import helpers, jobs_router

HOME = str(Path.home())


class _NoDelivery:
    async def deliver(self, job: object, result: object) -> None:
        pass


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    store = InMemoryCronStore()
    scheduler = CronScheduler(store=store, runners={}, delivery=_NoDelivery(), config=CronConfig())
    manager = CronManager(store, scheduler, shell_enabled=True)
    app = FastAPI()
    app.include_router(jobs_router, prefix="/cron")
    with patch.object(helpers, "_get_manager", return_value=manager):
        yield TestClient(app)


def _job_body(**overrides: object) -> dict[str, object]:
    return {
        "name": "digest",
        "job_type": "agent",
        "schedule": {"kind": "interval", "interval_ms": 60_000},
        "prompt": "summarize the notes",
        **overrides,
    }


def _refusal(response: Response) -> str:
    """The ``issue`` a 400 names for ``allowed_roots``."""
    assert response.status_code == 400, response.text
    (detail,) = response.json()["detail"]["error"]["details"]
    assert detail["field"] == "allowed_roots"
    return str(detail["issue"])


class TestCreate:
    @pytest.mark.parametrize(
        ("root", "issue"),
        [
            (HOME, "too_broad"),
            ("/", "too_broad"),
            ("~", "too_broad"),
            (os.path.join(HOME, ".ssh"), "dangerous"),
            ("notes", "not_absolute"),
        ],
    )
    def test_a_root_the_gate_refuses_is_refused(self, client: TestClient, root: str, issue: str) -> None:
        response = client.post("/cron/", json=_job_body(allowed_roots=["/tmp", root]))

        assert _refusal(response) == issue

    def test_ordinary_roots_are_stored_as_given(self, client: TestClient, tmp_path: Path) -> None:
        roots = ["~/Documents", str(tmp_path), str(tmp_path / "created-later")]

        response = client.post("/cron/", json=_job_body(allowed_roots=roots))

        assert response.status_code == 201, response.text
        assert response.json()["allowed_roots"] == roots

    def test_a_root_may_name_a_single_file(self, client: TestClient, tmp_path: Path) -> None:
        note = tmp_path / "todo.md"
        note.write_text("x", encoding="utf-8")

        response = client.post("/cron/", json=_job_body(allowed_roots=[str(note)]))

        assert response.status_code == 201, response.text

    def test_a_job_without_roots_is_unaffected(self, client: TestClient) -> None:
        assert client.post("/cron/", json=_job_body()).status_code == 201


class TestUpdate:
    def test_changing_the_roots_to_a_broad_one_is_refused(self, client: TestClient) -> None:
        job_id = client.post("/cron/", json=_job_body()).json()["id"]

        response = client.patch(f"/cron/{job_id}", json={"allowed_roots": [HOME]})

        assert _refusal(response) == "too_broad"

    def test_an_update_that_leaves_the_roots_alone_is_not_judged_by_them(self, client: TestClient, tmp_path: Path) -> None:
        job_id = client.post("/cron/", json=_job_body(allowed_roots=[str(tmp_path)])).json()["id"]

        response = client.patch(f"/cron/{job_id}", json={"name": "renamed"})

        assert response.status_code == 200, response.text
        assert response.json()["allowed_roots"] == [str(tmp_path)]

    def test_clearing_the_roots_is_allowed(self, client: TestClient, tmp_path: Path) -> None:
        job_id = client.post("/cron/", json=_job_body(allowed_roots=[str(tmp_path)])).json()["id"]

        response = client.patch(f"/cron/{job_id}", json={"allowed_roots": []})

        assert response.status_code == 200, response.text
        assert response.json()["allowed_roots"] == []
