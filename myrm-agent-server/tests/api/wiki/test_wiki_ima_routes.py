"""ima REST routes: error contract, write-only credentials and request plumbing."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_optional_llm_for_user
from app.api.wiki.routes.ima import router
from app.services.wiki.source_sync import ima
from app.services.wiki.source_sync.ima.schemas import ImaItemCounts, ImaJobStatus, ImaLibrary, ImaStatus

SECRET = "super-secret-api-key"


def make_status(**overrides: object) -> ImaStatus:
    base: dict[str, object] = {
        "connected": True,
        "account_hint": "abcd…wxyz",
        "knowledge_bases": [],
        "job": ImaJobStatus(),
        "counts": ImaItemCounts(),
    }
    return ImaStatus.model_validate({**base, **overrides})


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_optional_llm_for_user] = lambda: object()
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


def patched(name: str, **kwargs: object):
    return patch(f"app.api.wiki.routes.ima.ima.{name}", new=AsyncMock(**kwargs))


def test_status_is_returned_as_is(client: TestClient) -> None:
    with patched("build_status", return_value=make_status()) as build:
        response = client.get("/sources/ima", params={"agent_id": "agent-1"})

    assert response.status_code == 200 and response.json()["account_hint"] == "abcd…wxyz"
    build.assert_awaited_once_with("agent-1")


def test_saving_credentials_validates_then_returns_status_without_echoing_the_key(client: TestClient) -> None:
    with patched("connect") as connect, patched("build_status", return_value=make_status()):
        response = client.put("/sources/ima/credentials", json={"client_id": "cid", "api_key": SECRET})

    assert response.status_code == 200
    assert SECRET not in response.text
    connect.assert_awaited_once_with(client_id="cid", api_key=SECRET, agent_id=None)


@pytest.mark.parametrize(
    ("error", "status_code", "code"),
    [
        (ima.ImaAuthError("upstream said: key abc is invalid"), 400, "ima_auth_failed"),
        (ima.ImaRateLimitError("slow"), 429, "ima_rate_limited"),
        (ima.ImaTransientError("socket closed by 10.0.0.1"), 502, "ima_unreachable"),
        (ima.ImaPermanentError("code 999: internal detail"), 502, "ima_unreachable"),
        (ima.ImaOperationError("ima_not_connected", "ima is not connected"), 400, "ima_not_connected"),
        (ima.ImaOperationError("dedup_review_required", "resolve duplicates"), 409, "dedup_review_required"),
        (ValueError("Cron job limit reached for the current plan"), 409, "sync_unavailable"),
        (RuntimeError("database exploded at /secret/path"), 500, "ima_failed"),
    ],
)
def test_failures_map_to_stable_codes_and_never_leak_upstream_text(
    client: TestClient, error: Exception, status_code: int, code: str
) -> None:
    with patched("connect", side_effect=error):
        response = client.put("/sources/ima/credentials", json={"client_id": "cid", "api_key": SECRET})

    assert response.status_code == status_code
    assert response.json()["detail"]["code"] == code
    leaked = ("upstream said", "10.0.0.1", "internal detail", "/secret/path", SECRET)
    assert not any(fragment in response.text for fragment in leaked)


def test_a_refusal_from_the_cron_manager_is_logged_with_its_reason(client: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    refusal = ValueError("ROUTER job requires a non-empty 'prompt'")
    with caplog.at_level(logging.WARNING, logger="app.api.wiki.routes.ima"), patched("start_sync", side_effect=refusal):
        response = client.post("/sources/ima/sync/start", json={"locale": "en"})

    assert response.status_code == 409 and response.json()["detail"]["code"] == "sync_unavailable"
    assert [record.levelno for record in caplog.records] == [logging.WARNING]
    assert "requires a non-empty 'prompt'" in caplog.text


def test_libraries_and_disconnect(client: TestClient) -> None:
    with patched("list_libraries", return_value=[ImaLibrary(id="kb1", name="Notes")]):
        assert client.get("/sources/ima/libraries").json() == [{"id": "kb1", "name": "Notes"}]

    with patched("disconnect") as disconnect, patched("build_status", return_value=make_status(connected=False)):
        response = client.delete("/sources/ima/credentials")
    assert response.status_code == 200 and response.json()["connected"] is False
    disconnect.assert_awaited_once()


def test_config_and_sync_controls_pass_agent_and_locale(client: TestClient) -> None:
    with patched("save_selection") as save, patched("build_status", return_value=make_status()):
        assert (
            client.put(
                "/sources/ima/config", json={"library_ids": ["kb1"], "include_notes": False}, params={"agent_id": "a"}
            ).status_code
            == 200
        )
    save.assert_awaited_once_with(library_ids=["kb1"], include_notes=False, agent_id="a")

    with patched("start_sync") as start, patched("build_status", return_value=make_status()):
        assert client.post("/sources/ima/sync/start", json={"locale": "zh"}, params={"agent_id": "a"}).status_code == 202
    start.assert_awaited_once_with(agent_id="a", locale="zh")

    for action, name in (("pause", "pause_sync"), ("resume", "resume_sync")):
        with patched(name) as call, patched("build_status", return_value=make_status()):
            assert client.post(f"/sources/ima/sync/{action}").status_code in {200, 202}
        call.assert_awaited_once_with(agent_id=None)


def test_unstarted_sync_cannot_be_paused(client: TestClient) -> None:
    with patched("pause_sync", side_effect=ima.ImaOperationError("ima_sync_not_started", "sync has not been started")):
        response = client.post("/sources/ima/sync/pause")
    assert response.status_code == 400 and response.json()["detail"]["code"] == "ima_sync_not_started"


def test_retry_failed_and_compile_report_counts(client: TestClient) -> None:
    with patched("retry_failed", return_value=4):
        assert client.post("/sources/ima/sync/retry-failed").json() == {"count": 4}
    with patched("compile_imported", return_value=7) as compile_call:
        response = client.post("/sources/ima/compile", params={"agent_id": "a"})
    assert response.status_code == 202 and response.json() == {"count": 7}
    assert compile_call.await_args.kwargs["agent_id"] == "a"


def test_items_bucket_is_validated(client: TestClient) -> None:
    with patched("list_items", return_value=[]) as listing:
        assert client.get("/sources/ima/items", params={"bucket": "lossy"}).status_code == 200
        assert client.get("/sources/ima/items", params={"bucket": "everything"}).status_code == 422
    listing.assert_awaited_once_with(None, "lossy")


def test_request_bodies_are_bounded(client: TestClient) -> None:
    assert client.put("/sources/ima/credentials", json={"client_id": "x" * 300, "api_key": "k"}).status_code == 422
    assert client.put("/sources/ima/config", json={"library_ids": ["k"] * 51}).status_code == 422
