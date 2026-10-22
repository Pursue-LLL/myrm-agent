"""HTTP surface of the instance archive: full flow, error codes, layout guard, pair-token default-deny."""

from __future__ import annotations

import time
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.api.instance_archive import router as router_module
from app.api.instance_archive.router import router
from app.remote_access.mobile_gate import is_mobile_remote_control_path
from app.services.config.encryption import ConfigEncryptionService
from app.services.instance_archive import ArchivePaths, Operation, OutcomeStatus, PromotionOutcome, export_jobs, export_service
from tests.services.instance_archive.conftest import TARGET_KEY

PASSPHRASE = "correct horse battery"
_CHUNK = 64 * 1024


def _settings(state: Path, *, sqlite_path: Path | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        database=SimpleNamespace(state_dir=str(state), sqlite_path=str(sqlite_path or state / "data.db")),
        app_version="1.0.0",
    )


@pytest.fixture
def client_for(monkeypatch: pytest.MonkeyPatch) -> Iterator[object]:
    export_jobs._managers.clear()

    def build(state: Path, *, local: bool = True, sqlite_path: Path | None = None) -> TestClient:
        monkeypatch.setattr(router_module, "get_settings", lambda: _settings(state, sqlite_path=sqlite_path))
        monkeypatch.setattr(router_module, "is_local_mode", lambda: local)
        monkeypatch.setattr(router_module, "is_sandbox", lambda: not local)
        monkeypatch.setattr(
            router_module,
            "get_encryption_service",
            lambda: ConfigEncryptionService(TARGET_KEY, is_sandbox=not local, is_local=local),
        )
        app = FastAPI()

        @app.middleware("http")
        async def identity(request: Request, call_next):  # noqa: ANN001, ANN202
            request.state.user_id = "user-a"
            return await call_next(request)

        app.include_router(router, prefix="/api/v1/instance-archive")
        return TestClient(app)

    yield build
    export_jobs._managers.clear()


def _finished_export(client: TestClient, passphrase: str | None) -> dict[str, object]:
    started = client.post("/api/v1/instance-archive/exports", json={"passphrase": passphrase})
    assert started.status_code == 200, started.text
    job_id = started.json()["job_id"]
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        job = client.get(f"/api/v1/instance-archive/exports/{job_id}").json()
        if job["state"] != "running":
            break
        time.sleep(0.05)
    assert job["state"] == "done", job
    assert job["size_bytes"] and job["files_done"] == job["files_total"]
    return job


def _export(client: TestClient, passphrase: str | None) -> bytes:
    job = _finished_export(client, passphrase)
    job_id = job["job_id"]
    download = client.get(f"/api/v1/instance-archive/exports/{job_id}/download")
    assert download.status_code == 200
    assert download.headers["content-type"] == "application/zip"
    assert client.delete(f"/api/v1/instance-archive/exports/{job_id}").status_code == 204
    assert client.get(f"/api/v1/instance-archive/exports/{job_id}").status_code == 404
    return download.content


def _upload(client: TestClient, data: bytes) -> str:
    created = client.post("/api/v1/instance-archive/imports", json={"size_bytes": len(data), "chunk_bytes": _CHUNK})
    assert created.status_code == 200, created.text
    session = created.json()
    for index in range(session["chunk_count"]):
        chunk = data[index * _CHUNK : (index + 1) * _CHUNK]
        response = client.put(f"/api/v1/instance-archive/imports/{session['session_id']}/chunks/{index}", content=chunk)
        assert response.status_code == 200, response.text
    return session["session_id"]


def test_status_reports_capabilities(client_for, target_state: Path) -> None:  # noqa: ANN001
    body = client_for(target_state).get("/api/v1/instance-archive/status").json()
    assert body == {
        "supported": True,
        "can_protect_secrets": True,
        "restart_mode": "process",
        "pending_operation": None,
        "rollback_available": False,
    }
    sandbox = client_for(target_state, local=False).get("/api/v1/instance-archive/status").json()
    assert sandbox["can_protect_secrets"] is False
    assert sandbox["restart_mode"] == "sandbox"


def test_full_http_flow_from_export_to_queued_swap(client_for, source_state: Path, target_state: Path) -> None:  # noqa: ANN001
    archive = _export(client_for(source_state), PASSPHRASE)

    client = client_for(target_state)
    session_id = _upload(client, archive)
    base = f"/api/v1/instance-archive/imports/{session_id}"

    missing = client.post(f"{base}/stage", json={})
    assert (missing.status_code, missing.json()["detail"]["code"]) == (400, "passphrase_required")
    wrong = client.post(f"{base}/stage", json={"passphrase": "wrong wrong wrong"})
    assert wrong.json()["detail"]["code"] == "wrong_passphrase"

    staged = client.post(f"{base}/stage", json={"passphrase": PASSPHRASE})
    assert staged.status_code == 200, staged.text
    report = staged.json()
    assert set(report) == {
        "session_id",
        "created_at",
        "counts",
        "current_counts",
        "executable",
        "reentry",
        "paused_jobs",
        "missing_paths",
        "unreadable_count",
        "identity_dropped",
        "config_key_carried",
    }  # the frontend `ImportReport` type
    assert report["created_at"] and report["counts"]["cron_jobs"] == 1
    assert report["paused_jobs"] == 1
    assert report["unreadable_count"] == 0
    assert report["executable"]["scheduled_commands"] == 1
    assert client.get(base).json()["state"] == "staged"

    refused = client.post(f"{base}/confirm", json={"acknowledge_executables": False})
    assert (refused.status_code, refused.json()["detail"]["code"]) == (409, "acknowledgement_required")

    confirmed = client.post(f"{base}/confirm", json={"acknowledge_executables": True})
    assert confirmed.json() == {"operation": "import", "requires_restart": True}
    assert client.get("/api/v1/instance-archive/status").json()["pending_operation"] == "import"
    assert ArchivePaths(target_state).pending.exists()

    assert client.delete(base).status_code == 204  # cancelling a confirmed import withdraws the marker
    assert not ArchivePaths(target_state).pending.exists()
    assert client.get(base).status_code == 404


def test_an_export_reports_how_many_carried_items_it_could_not_include(
    client_for,  # noqa: ANN001
    source_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = client_for(source_state)
    assert _finished_export(client, None)["unreadable_count"] == 0

    real_scan = export_service.scan_state_dir
    monkeypatch.setattr(
        export_service,
        "scan_state_dir",
        lambda state_dir: replace(real_scan(state_dir), unreadable=["wiki/private", "skills/sealed"]),
    )

    assert _finished_export(client, None)["unreadable_count"] == 2


def test_invalid_requests_map_to_stable_codes(client_for, target_state: Path) -> None:  # noqa: ANN001
    client = client_for(target_state)
    session = client.post("/api/v1/instance-archive/imports", json={"size_bytes": 100, "chunk_bytes": 100}).json()

    short = client.put(f"/api/v1/instance-archive/imports/{session['session_id']}/chunks/0", content=b"x")
    assert (short.status_code, short.json()["detail"]["code"]) == (400, "invalid_chunk")
    unknown = client.get(f"/api/v1/instance-archive/imports/{'0' * 32}")
    assert (unknown.status_code, unknown.json()["detail"]["code"]) == (404, "unknown_session")
    traversal = client.get("/api/v1/instance-archive/imports/..%2F..")
    assert traversal.status_code in (404, 400)
    early = client.post(f"/api/v1/instance-archive/imports/{session['session_id']}/stage", json={})
    assert early.json()["detail"]["code"] == "upload_incomplete"


def test_passphrase_is_refused_where_secrets_cannot_travel(client_for, source_state: Path) -> None:  # noqa: ANN001
    response = client_for(source_state, local=False).post("/api/v1/instance-archive/exports", json={"passphrase": PASSPHRASE})
    assert (response.status_code, response.json()["detail"]["code"]) == (400, "secrets_unavailable")


def test_custom_database_location_disables_the_feature(client_for, target_state: Path, tmp_path: Path) -> None:  # noqa: ANN001
    client = client_for(target_state, sqlite_path=tmp_path / "elsewhere" / "data.db")

    assert client.get("/api/v1/instance-archive/status").json()["supported"] is False
    blocked = client.post("/api/v1/instance-archive/exports", json={})
    assert (blocked.status_code, blocked.json()["detail"]["code"]) == (409, "unsupported_layout")


def test_rollback_without_a_previous_swap_is_a_conflict(client_for, target_state: Path) -> None:  # noqa: ANN001
    response = client_for(target_state).post("/api/v1/instance-archive/rollback")
    assert (response.status_code, response.json()["detail"]["code"]) == (409, "nothing_to_undo")


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/instance-archive/status",
        "/api/v1/instance-archive/exports",
        "/api/v1/instance-archive/exports/abc/download",
        "/api/v1/instance-archive/imports",
        "/api/v1/instance-archive/imports/abc/chunks/0",
        "/api/v1/instance-archive/imports/abc/confirm",
        "/api/v1/instance-archive/rollback",
        "/api/v1/instance-archive/auto-backup",
        "/api/v1/instance-archive/auto-backup/run",
        "/api/v1/system/storage/snapshots/snap_x/restore",
    ],
)
def test_pair_tokens_never_reach_backup_endpoints(path: str) -> None:
    assert not is_mobile_remote_control_path(path)


def test_outcome_is_delivered_once_then_cleared(client_for, target_state: Path) -> None:  # noqa: ANN001
    client = client_for(target_state)
    assert client.get("/api/v1/instance-archive/outcome").json() == {"outcome": None}

    PromotionOutcome(
        operation=Operation.IMPORT,
        status=OutcomeStatus.RESTORED,
        completed_at="2026-10-12T00:00:00+00:00",
        summary={"chats": 3},
        reentry=("config:providers",),
        rollback_available=True,
    ).save(ArchivePaths(target_state).result)

    shown = client.get("/api/v1/instance-archive/outcome").json()["outcome"]
    assert (shown["status"], shown["summary"], shown["reentry"], shown["rollback_available"]) == (
        "restored",
        {"chats": 3},
        ["config:providers"],
        True,
    )
    assert client.post("/api/v1/instance-archive/outcome/acknowledge").status_code == 204
    assert client.get("/api/v1/instance-archive/outcome").json() == {"outcome": None}
