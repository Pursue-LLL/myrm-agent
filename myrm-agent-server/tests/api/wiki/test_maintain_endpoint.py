"""POST /wiki/maintain starts a background run (202), GET /wiki/maintain/status reports it and POST /wiki/maintain/cancel stops it."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from myrm_agent_harness.toolkits.wiki.maintenance.modes import MaintainMode
from myrm_agent_harness.toolkits.wiki.maintenance.progress import MaintainPhase, MaintainProgress

from app.api.dependencies import get_optional_llm_for_user
from app.core.security.auth.identity import LOCAL_USER_ID
from app.services.wiki.maintain import WikiMaintainRunResult, WikiMaintainScheduleResult, run_registry
from app.services.wiki.maintain.run_registry import MaintainRun, start_wiki_maintain_run

_SCHEDULE = "app.services.wiki.maintain.schedule_wiki_maintain"


@dataclass(frozen=True, slots=True)
class _FakeIdentity:
    user_id: str = LOCAL_USER_ID
    auth_source: str = "loopback"
    loopback: bool = True
    client_ip: str = "127.0.0.1"
    private_net: bool = False


@pytest.fixture(autouse=True)
def _bypass_auth() -> Iterator[None]:
    with patch(
        "app.middleware.auth.resolve_identity",
        return_value=_FakeIdentity(),
    ):
        yield


@pytest.fixture(autouse=True)
def _clean_registry() -> Iterator[None]:
    run_registry._runs.clear()
    yield
    run_registry._runs.clear()


@pytest.fixture
def client() -> Iterator[TestClient]:
    from tests.support.minimal_app import build_minimal_app

    test_client = TestClient(build_minimal_app(preset="wiki"))
    test_client.app.dependency_overrides[get_optional_llm_for_user] = lambda: MagicMock()
    yield test_client
    test_client.app.dependency_overrides.pop(get_optional_llm_for_user, None)


def _run(mode: str = "structural", agent_id: str | None = None) -> MaintainRun:
    run = start_wiki_maintain_run(agent_id, mode)  # type: ignore[arg-type]
    assert run is not None
    return run


def test_maintain_default_structural_mode_is_accepted_in_the_background(client: TestClient) -> None:
    run = _run("structural")

    with patch(_SCHEDULE, new=MagicMock(return_value=WikiMaintainScheduleResult(run=run))) as schedule:
        response = client.post("/api/v1/wiki/maintain")

    assert response.status_code == 202
    assert response.json()["state"] == "running"
    assert response.json()["mode"] == "structural"
    assert schedule.call_args.kwargs["mode"] == MaintainMode.STRUCTURAL
    assert schedule.call_args.kwargs["agent_id"] is None


def test_maintain_full_mode_query_and_agent_scope_reach_the_scheduler(client: TestClient) -> None:
    run = _run("full", agent_id="agent-7")

    with patch(_SCHEDULE, new=MagicMock(return_value=WikiMaintainScheduleResult(run=run))) as schedule:
        response = client.post("/api/v1/wiki/maintain?mode=full&agent_id=agent-7")

    assert response.status_code == 202
    assert response.json()["mode"] == "full"
    assert schedule.call_args.kwargs["mode"] == MaintainMode.FULL
    assert schedule.call_args.kwargs["agent_id"] == "agent-7"


def test_maintain_while_a_run_is_in_flight_returns_that_runs_progress(client: TestClient) -> None:
    run = _run("full")
    run.on_progress(MaintainProgress(MaintainPhase.LINK_DISCOVERY, 7, 20))

    with patch(_SCHEDULE, new=MagicMock(return_value=WikiMaintainScheduleResult(run=run))):
        response = client.post("/api/v1/wiki/maintain?mode=full")

    body = response.json()
    assert response.status_code == 202
    assert (body["phase"], body["done"], body["total"]) == ("link_discovery", 7, 20)


def test_maintain_compile_busy_returns_409(client: TestClient) -> None:
    refused = WikiMaintainScheduleResult(skipped_reason="compile_in_progress")

    with patch(_SCHEDULE, new=MagicMock(return_value=refused)):
        response = client.post("/api/v1/wiki/maintain")

    assert response.status_code == 409
    assert "compilation is in progress" in response.json()["detail"].lower()


def test_status_is_idle_before_any_run(client: TestClient) -> None:
    response = client.get("/api/v1/wiki/maintain/status")

    assert response.status_code == 200
    assert response.json() == {
        "state": "idle",
        "mode": None,
        "phase": None,
        "done": 0,
        "total": 0,
        "result": None,
        "error_code": None,
    }


def test_status_reports_a_running_run_with_its_progress(client: TestClient) -> None:
    run = _run("full")
    run.on_progress(MaintainProgress(MaintainPhase.DRIFT_REVIEW, 2, 5))

    body = client.get("/api/v1/wiki/maintain/status").json()

    assert body["state"] == "running"
    assert (body["mode"], body["phase"], body["done"], body["total"]) == ("full", "drift_review", 2, 5)
    assert body["result"] is None


def test_status_of_a_finished_run_carries_the_maintenance_result(client: TestClient) -> None:
    run = _run("full")
    run.finish(
        WikiMaintainRunResult(
            mode="full",
            issues_found=1,
            issues_fixed=0,
            connections_discovered=2,
            duration_ms=12,
            open_actions_count=1,
            raw_security_removed=1,
            raw_security_removed_paths=["raw/secret.md"],
            lint_issues=[
                {
                    "issue_type": "broken_link",
                    "severity": "medium",
                    "location": "notes/alpha",
                    "description": "Broken link to missing.md",
                    "action_kind": "navigate",
                    "suggested_fix": None,
                }
            ],
        )
    )

    body = client.get("/api/v1/wiki/maintain/status").json()

    assert body["state"] == "succeeded"
    assert body["error_code"] is None
    assert body["result"]["connections_discovered"] == 2
    assert body["result"]["open_actions_count"] == 1
    assert body["result"]["raw_security_removed_paths"] == ["raw/secret.md"]
    assert body["result"]["issues"][0]["action_kind"] == "navigate"
    assert body["result"]["issues"][0]["suggested_fix"] is None


def test_status_of_a_run_the_model_never_answered_says_so(client: TestClient) -> None:
    run = _run("full")
    run.finish(WikiMaintainRunResult(mode="full", issues_found=2, issues_fixed=1, ai_unavailable=True))

    body = client.get("/api/v1/wiki/maintain/status").json()

    assert body["state"] == "succeeded"
    assert body["result"]["ai_unavailable"] is True
    assert body["result"]["issues_fixed"] == 1


def test_status_of_a_finished_run_is_available_unless_the_model_never_answered(client: TestClient) -> None:
    run = _run("full")
    run.finish(WikiMaintainRunResult(mode="full"))

    assert client.get("/api/v1/wiki/maintain/status").json()["result"]["ai_unavailable"] is False


def test_cancel_asks_the_running_run_to_stop_and_keeps_reporting_it_as_running(client: TestClient) -> None:
    run = _run("full")
    run.on_progress(MaintainProgress(MaintainPhase.LINK_DISCOVERY, 4, 20))

    response = client.post("/api/v1/wiki/maintain/cancel")

    assert response.status_code == 200
    body = response.json()
    assert (body["state"], body["phase"], body["done"], body["total"]) == ("running", "link_discovery", 4, 20)
    assert run.stop.is_set()


def test_cancel_can_be_repeated_and_never_fails(client: TestClient) -> None:
    run = _run("full")

    first = client.post("/api/v1/wiki/maintain/cancel")
    second = client.post("/api/v1/wiki/maintain/cancel")

    assert (first.status_code, second.status_code) == (200, 200)
    assert second.json() == first.json()
    assert run.stop.is_set()


def test_cancel_without_a_run_reports_idle(client: TestClient) -> None:
    response = client.post("/api/v1/wiki/maintain/cancel")

    assert response.status_code == 200
    assert response.json()["state"] == "idle"


def test_cancel_after_the_run_finished_changes_nothing(client: TestClient) -> None:
    run = _run("full")
    run.finish(WikiMaintainRunResult(mode="full", connections_discovered=2))

    body = client.post("/api/v1/wiki/maintain/cancel").json()

    assert body["state"] == "succeeded"
    assert body["result"]["connections_discovered"] == 2
    assert not run.stop.is_set()


def test_status_of_a_cancelled_run_carries_what_it_wrote_before_stopping(client: TestClient) -> None:
    run = _run("full")
    run.finish(WikiMaintainRunResult(mode="full", issues_found=3, issues_fixed=1, connections_discovered=2, cancelled=True))

    body = client.get("/api/v1/wiki/maintain/status").json()

    assert body["state"] == "cancelled"
    assert body["error_code"] is None
    assert (body["result"]["issues_fixed"], body["result"]["connections_discovered"]) == (1, 2)


def test_status_of_a_failed_run_is_an_error_code_without_exception_text(client: TestClient) -> None:
    run = _run("full")
    run.fail("maintain_failed")

    body = client.get("/api/v1/wiki/maintain/status").json()

    assert body["state"] == "failed"
    assert body["error_code"] == "maintain_failed"
    assert body["result"] is None


def test_status_is_scoped_to_the_agent(client: TestClient) -> None:
    _run("full", agent_id="agent-1")

    assert client.get("/api/v1/wiki/maintain/status?agent_id=agent-1").json()["state"] == "running"
    assert client.get("/api/v1/wiki/maintain/status?agent_id=agent-2").json()["state"] == "idle"
    assert client.get("/api/v1/wiki/maintain/status").json()["state"] == "idle"
