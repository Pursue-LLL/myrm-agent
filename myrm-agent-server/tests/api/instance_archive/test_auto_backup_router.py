"""HTTP surface of the scheduled backup: settings, first backup on enable, run now, availability."""

from __future__ import annotations

import shutil
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.instance_archive.router import router
from app.services.instance_archive import ArchivePaths, export_jobs
from app.services.instance_archive.auto_backup import service as service_module

URL = "/api/v1/instance-archive/auto-backup"
BODY = {"enabled": True, "frequency": "daily", "keep": 3, "directory": None}


@pytest.fixture
def client_for(monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[..., TestClient]]:
    monkeypatch.setattr(service_module, "_services", {})
    monkeypatch.setattr(export_jobs, "_managers", {})

    def build(state: Path, *, sandbox: bool = False) -> TestClient:
        settings = SimpleNamespace(
            database=SimpleNamespace(state_dir=str(state), sqlite_path=str(state / "data.db")), app_version="1.0.0"
        )
        monkeypatch.setattr(service_module, "get_settings", lambda: settings)
        monkeypatch.setattr(service_module, "is_sandbox", lambda: sandbox)
        app = FastAPI()
        app.include_router(router, prefix="/api/v1/instance-archive")
        return TestClient(app)

    yield build


def _settled(client: TestClient, *, expect_backups: int) -> dict[str, object]:
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        view = client.get(URL).json()
        if not view["running"] and len(view["backups"]) >= expect_backups and view["last_success_at"]:
            return view
        time.sleep(0.1)
    raise AssertionError("backup did not finish")


def test_a_fresh_instance_is_off_with_the_default_folder(client_for, source_state: Path) -> None:  # noqa: ANN001
    view = client_for(source_state).get(URL).json()

    assert view["supported"] is True and view["enabled"] is False
    assert (view["frequency"], view["keep"], view["default_directory"]) == ("daily", 3, True)
    assert view["directory"].endswith("backups/instance")
    assert view["backups"] == [] and view["last_success_at"] is None and view["running"] is False


def test_turning_it_on_backs_up_right_away_and_lists_the_file(client_for, source_state: Path) -> None:  # noqa: ANN001
    client = client_for(source_state)

    put = client.put(URL, json=BODY)
    assert put.status_code == 200 and put.json()["enabled"] is True

    view = _settled(client, expect_backups=1)
    [backup] = view["backups"]
    stored = Path(view["directory"]) / backup["name"]
    assert backup["size_bytes"] == stored.stat().st_size == view["last_success_size"]
    assert backup["name"].startswith("myrm-auto-backup-") and backup["created_at"]
    assert view["consecutive_failures"] == 0 and view["last_error_code"] is None and view["overdue"] is False


def test_a_folder_that_cannot_be_read_is_reported_as_unavailable_not_as_empty(client_for, source_state: Path) -> None:  # noqa: ANN001
    client = client_for(source_state)
    client.put(URL, json=BODY)
    view = _settled(client, expect_backups=1)
    assert view["folder_available"] is True

    shutil.rmtree(view["directory"])
    gone = client.get(URL).json()

    assert gone["folder_available"] is False and gone["enabled"] is True
    assert gone["backups"] == [] and gone["last_success_at"] is None
    assert gone["overdue"] is False and gone["consecutive_failures"] == 0


def test_settings_are_validated_at_the_boundary(client_for, source_state: Path) -> None:  # noqa: ANN001
    client = client_for(source_state)

    unusable_folders = ("x" * 2000, "/Volumes/a\x00b")  # too long; a NUL byte no filesystem call accepts
    for bad in (
        {**BODY, "keep": 0},
        {**BODY, "keep": 11},
        {**BODY, "frequency": "hourly"},
        *({**BODY, "enabled": enabled, "directory": folder} for folder in unusable_folders for enabled in (True, False)),
    ):
        assert client.put(URL, json=bad).status_code == 422
    assert client.get(URL).status_code == 200  # nothing unreadable was saved

    saved = client.put(URL, json={**BODY, "enabled": False, "directory": "   "}).json()
    assert saved["default_directory"] is True and saved["enabled"] is False


def test_a_folder_inside_the_app_data_is_refused_with_a_stable_code(client_for, source_state: Path) -> None:  # noqa: ANN001
    client = client_for(source_state)

    response = client.put(URL, json={**BODY, "directory": str(source_state / "skills")})

    assert (response.status_code, response.json()["detail"]["code"]) == (400, "backup_dir_inside_state")
    assert client.get(URL).json()["enabled"] is False


def test_a_home_that_cannot_be_determined_keeps_the_settings_readable_and_is_refused_as_a_folder(  # noqa: ANN001
    client_for, source_state: Path
) -> None:
    client = client_for(source_state)
    typo = "~no-such-user-4f1d9c/Backups"

    saved = client.put(URL, json={**BODY, "enabled": False, "directory": typo})
    assert saved.status_code == 200
    assert (saved.json()["directory"], saved.json()["folder_available"]) == (typo, False)
    assert client.get(URL).status_code == 200

    refused = client.put(URL, json={**BODY, "directory": typo})
    assert (refused.status_code, refused.json()["detail"]["code"]) == (400, "backup_dir_invalid")


def test_run_now_works_with_the_schedule_off(client_for, source_state: Path) -> None:  # noqa: ANN001
    client = client_for(source_state)

    response = client.post(f"{URL}/run")

    assert response.status_code == 200 and response.json()["running"] is True
    assert len(_settled(client, expect_backups=1)["backups"]) == 1


def test_run_now_reports_a_busy_exporter_and_a_bad_folder(  # noqa: ANN001
    client_for, source_state: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = client_for(source_state)
    wiki = str(source_state / "wiki")
    client.put(URL, json={**BODY, "enabled": False})
    assert client.put(URL, json={**BODY, "enabled": False, "directory": wiki}).status_code == 200
    bad = client.post(f"{URL}/run")
    assert (bad.status_code, bad.json()["detail"]["code"]) == (400, "backup_dir_inside_state")

    client.put(URL, json={**BODY, "enabled": False, "directory": None})
    gate = threading.Event()
    real = export_jobs.build_export

    def slow(**kwargs: object):
        gate.wait(30)
        return real(**kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(export_jobs, "build_export", slow)
    manager = export_jobs.get_export_manager(ArchivePaths(source_state))
    manual = manager.start(user_id="local-user", app_version="1", deploy_mode="local", config_key=None, passphrase=None)
    try:
        busy = client.post(f"{URL}/run")
        assert (busy.status_code, busy.json()["detail"]["code"]) == (409, "export_busy")
    finally:
        gate.set()
        manual.done.wait(30)
        manager.discard(manual.job_id)


def test_a_cloud_sandbox_is_told_it_is_unsupported_and_cannot_write(client_for, source_state: Path) -> None:  # noqa: ANN001
    client = client_for(source_state, sandbox=True)

    assert client.get(URL).json() == {
        "supported": False,
        "enabled": False,
        "frequency": "daily",
        "keep": 3,
        "directory": "",
        "default_directory": True,
        "folder_available": True,
        "running": False,
        "overdue": False,
        "last_success_at": None,
        "last_success_size": None,
        "consecutive_failures": 0,
        "last_error_code": None,
        "backups": [],
    }
    for response in (client.put(URL, json=BODY), client.post(f"{URL}/run")):
        assert (response.status_code, response.json()["detail"]["code"]) == (409, "unsupported_layout")
