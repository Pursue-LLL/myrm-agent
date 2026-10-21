"""POST /skills/{skill_id}/reveal opens the skill's directory in the OS file manager."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.skills.core import router


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/skills")
    return TestClient(app)


def _reveal(client: TestClient, skill: SimpleNamespace | None, *, local_mode: bool = True):
    """Call the endpoint with the skill lookup stubbed and the OS launcher captured."""
    with (
        patch("app.config.deploy_mode.is_local_mode", return_value=local_mode),
        patch("app.api.skills.core.skills_service.get_skill", AsyncMock(return_value=skill)),
        patch("app.services.files.reveal_utils.subprocess.Popen") as launcher,
    ):
        return client.post("/api/v1/skills/skill-1/reveal"), launcher


def test_reveal_opens_the_skill_directory(client: TestClient, tmp_path: Path) -> None:
    response, launcher = _reveal(client, SimpleNamespace(storage_path=str(tmp_path)))

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "path": str(tmp_path.resolve())}
    (command,) = launcher.call_args.args
    assert str(tmp_path.resolve()) in command


def test_reveal_is_refused_outside_local_mode(client: TestClient, tmp_path: Path) -> None:
    response, launcher = _reveal(client, SimpleNamespace(storage_path=str(tmp_path)), local_mode=False)

    assert response.status_code == 403
    launcher.assert_not_called()


def test_reveal_unknown_skill_is_not_found(client: TestClient) -> None:
    response, launcher = _reveal(client, None)

    assert response.status_code == 404
    launcher.assert_not_called()


def test_reveal_skill_without_local_storage_is_rejected(client: TestClient) -> None:
    response, launcher = _reveal(client, SimpleNamespace(storage_path=None))

    assert response.status_code == 400
    launcher.assert_not_called()


def test_reveal_missing_directory_is_not_found(client: TestClient, tmp_path: Path) -> None:
    response, launcher = _reveal(client, SimpleNamespace(storage_path=str(tmp_path / "gone")))

    assert response.status_code == 404
    launcher.assert_not_called()
