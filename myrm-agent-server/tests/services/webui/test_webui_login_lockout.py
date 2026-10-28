"""Login lockout of WebuiAuthService: 5 failures per client lock that client for the rest of the window."""

from __future__ import annotations

import asyncio
from collections import Counter
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock, patch

import pytest
from fastapi import Request
from httpx import ASGITransport, AsyncClient

from app.config.deploy_mode import get_deploy_mode
from app.config.settings import settings
from app.services.webui.admin_store import save_admin
from app.services.webui.auth_service import WebuiAuthService
from app.services.webui.passwords import hash_password
from tests.support.minimal_app import build_minimal_app

_USERNAME = "admin"
_PASSWORD = "Str0ng!Pass"
_LOCK_MESSAGE = "Too many failed attempts. Retry after"


@pytest.fixture(autouse=True)
def _admin_account(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("DEPLOY_MODE", "local")
    monkeypatch.setenv("WEBUI_MODE", "false")
    monkeypatch.setenv("WEBUI_REMOTE_MODE", "false")
    monkeypatch.setattr(settings.database, "state_dir", str(tmp_path))
    get_deploy_mode.cache_clear()
    from app.platform_utils.deployment_capabilities import _reset_capabilities_cache_for_testing

    _reset_capabilities_cache_for_testing()
    save_admin(_USERNAME, hash_password(_PASSWORD))
    yield
    get_deploy_mode.cache_clear()
    _reset_capabilities_cache_for_testing()


def _request(host: str) -> Request:
    return cast(Request, SimpleNamespace(client=SimpleNamespace(host=host)))


def _fail_logins(service: WebuiAuthService, host: str, times: int) -> None:
    for _ in range(times):
        with pytest.raises(ValueError, match="Invalid username or password"):
            service.login(_request(host), username=_USERNAME, password="wrong")


def test_sixth_attempt_is_locked_even_with_the_correct_password() -> None:
    service = WebuiAuthService()
    _fail_logins(service, "10.0.0.1", 5)

    with pytest.raises(PermissionError, match=_LOCK_MESSAGE):
        service.login(_request("10.0.0.1"), username=_USERNAME, password=_PASSWORD)


def test_the_lock_is_reported_once_when_it_engages() -> None:
    service = WebuiAuthService()
    with patch("app.services.webui.auth_service.report_lockout", new=MagicMock()) as report:
        _fail_logins(service, "10.0.0.1", 4)
        report.assert_not_called()

        _fail_logins(service, "10.0.0.1", 1)
        report.assert_called_once_with("webui_login", client="10.0.0.1")

        with pytest.raises(PermissionError, match=_LOCK_MESSAGE):
            service.login(_request("10.0.0.1"), username=_USERNAME, password="wrong")
        report.assert_called_once()


def test_lock_message_reports_the_remaining_seconds() -> None:
    service = WebuiAuthService()
    _fail_logins(service, "10.0.0.1", 5)

    with pytest.raises(PermissionError) as exc_info:
        service.login(_request("10.0.0.1"), username=_USERNAME, password="wrong")

    assert exc_info.value.args[0].startswith(_LOCK_MESSAGE)
    seconds = int(exc_info.value.args[0].rsplit(" ", 2)[-2])
    assert 1 <= seconds <= 60


def test_other_clients_are_not_locked() -> None:
    service = WebuiAuthService()
    _fail_logins(service, "10.0.0.1", 5)

    assert service.login(_request("10.0.0.2"), username=_USERNAME, password=_PASSWORD) == _USERNAME


def test_four_failures_do_not_lock() -> None:
    service = WebuiAuthService()
    _fail_logins(service, "10.0.0.1", 4)

    assert service.login(_request("10.0.0.1"), username=_USERNAME, password=_PASSWORD) == _USERNAME


def test_successful_login_resets_the_failure_count() -> None:
    service = WebuiAuthService()
    _fail_logins(service, "10.0.0.1", 4)
    assert service.login(_request("10.0.0.1"), username=_USERNAME, password=_PASSWORD) == _USERNAME

    _fail_logins(service, "10.0.0.1", 4)
    assert service.login(_request("10.0.0.1"), username=_USERNAME, password=_PASSWORD) == _USERNAME


def test_wrong_username_counts_as_a_failure() -> None:
    service = WebuiAuthService()
    for _ in range(5):
        with pytest.raises(ValueError, match="Invalid username or password"):
            service.login(_request("10.0.0.1"), username="someone-else", password=_PASSWORD)

    with pytest.raises(PermissionError, match=_LOCK_MESSAGE):
        service.login(_request("10.0.0.1"), username=_USERNAME, password=_PASSWORD)


def test_missing_client_is_tracked_as_one_unknown_client() -> None:
    service = WebuiAuthService()
    no_client = cast(Request, SimpleNamespace(client=None))
    for _ in range(5):
        with pytest.raises(ValueError, match="Invalid username or password"):
            service.login(no_client, username=_USERNAME, password="wrong")

    with pytest.raises(PermissionError, match=_LOCK_MESSAGE):
        service.login(no_client, username=_USERNAME, password=_PASSWORD)


@pytest.mark.asyncio
async def test_login_route_answers_429_with_retry_after(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.api.webui.auth_routes.webui_auth_service", WebuiAuthService())
    transport = ASGITransport(app=build_minimal_app(webui=True))
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        for _ in range(5):
            bad = await client.post("/webui/auth/login", json={"username": _USERNAME, "password": "wrong"})
            assert bad.status_code == 401

        locked = await client.post("/webui/auth/login", json={"username": _USERNAME, "password": _PASSWORD})

    assert locked.status_code == 429
    assert 1 <= int(locked.headers["Retry-After"]) <= 60


@pytest.mark.asyncio
async def test_a_burst_of_concurrent_logins_gets_exactly_five_tries(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.api.webui.auth_routes.webui_auth_service", WebuiAuthService())
    transport = ASGITransport(app=build_minimal_app(webui=True))
    with patch("app.services.webui.auth_service.report_lockout", new=MagicMock()) as report:
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            burst = await asyncio.gather(
                *(client.post("/webui/auth/login", json={"username": _USERNAME, "password": f"wrong-{i}"}) for i in range(40))
            )
            correct = await client.post("/webui/auth/login", json={"username": _USERNAME, "password": _PASSWORD})

    assert Counter(response.status_code for response in burst) == {401: 5, 429: 35}
    assert correct.status_code == 429
    report.assert_called_once()
