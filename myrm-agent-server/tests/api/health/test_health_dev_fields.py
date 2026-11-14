"""Health endpoint exposes dev_mode and listen port for frontend diagnostics."""

from __future__ import annotations

import os
from collections.abc import Iterator
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="health")
from app.config.settings import settings
from app.server import runtime_dev_info
from app.server.runtime_dev_info import WEBUI_DEV_PORT, set_runtime_listen
from app.startup.listen_address import publish_listen_address


@pytest.fixture(autouse=True)
def _restore_runtime_listen(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """``set_runtime_listen`` writes PORT and HOST into the process environment and the listen state into its module,
    and every test that builds settings or reads the listen port afterwards would see them."""
    monkeypatch.setattr(runtime_dev_info, "_listen_port", runtime_dev_info._listen_port)
    monkeypatch.setattr(runtime_dev_info, "_dev_mode", runtime_dev_info._dev_mode)
    with patch.dict(os.environ):
        yield


def test_health_includes_runtime_dev_fields() -> None:
    set_runtime_listen(port=8080, host="127.0.0.1", dev_mode="split_dev")
    client = TestClient(app)
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert body["dev_mode"] == "split_dev"
    assert body["listen_port"] == 8080
    assert body["backend_port"] == 8080
    assert body["webui_dev_port"] == WEBUI_DEV_PORT


def test_health_uses_isolated_frontend_port(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MYRM_FRONTEND_PORT", "13000")
    monkeypatch.setenv("MYRM_RUNTIME_NAMESPACE", "runtime-health-test")
    set_runtime_listen(port=18080, host="127.0.0.1", dev_mode="split_dev")

    body = TestClient(app).get("/api/v1/health").json()

    assert body["backend_port"] == 18080
    assert body["webui_dev_port"] == 13000
    assert body["runtime_id"] == "runtime-health-test"


def test_sidecar_publishes_the_port_it_listens_on(monkeypatch: pytest.MonkeyPatch) -> None:
    """The packaged client may run on a non-default port; health must report that port, not the module default."""
    monkeypatch.setattr(settings, "port", 19080)
    with patch("app.startup.listen_address.is_webui_mode", return_value=False):
        assert publish_listen_address() == ("127.0.0.1", 19080)

    body = TestClient(app).get("/api/v1/health").json()
    assert body["listen_port"] == 19080
    assert body["backend_port"] == 19080
    assert body["dev_mode"] == "split_dev"


def test_webui_launch_publishes_standalone_mode_and_webui_port(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings.webui, "port", 25999)
    monkeypatch.setattr(settings.webui, "allow_remote", False)
    with patch("app.startup.listen_address.is_webui_mode", return_value=True):
        assert publish_listen_address() == ("127.0.0.1", 25999)

    body = TestClient(app).get("/api/v1/health").json()
    assert body["listen_port"] == 25999
    assert body["dev_mode"] == "standalone_webui"
    assert body["webui_dev_port"] is None


def test_remote_webui_launch_binds_every_interface(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings.webui, "port", 25999)
    monkeypatch.setattr(settings.webui, "allow_remote", True)
    with patch("app.startup.listen_address.is_webui_mode", return_value=True):
        assert publish_listen_address() == ("0.0.0.0", 25999)


def test_health_standalone_webui_ports() -> None:
    set_runtime_listen(port=25808, host="127.0.0.1", dev_mode="standalone_webui")
    client = TestClient(app)
    body = client.get("/api/v1/health").json()
    assert body["dev_mode"] == "standalone_webui"
    assert body["listen_port"] == 25808
    assert body["backend_port"] == 25808
    assert body["webui_dev_port"] is None
