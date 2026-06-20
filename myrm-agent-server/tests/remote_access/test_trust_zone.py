"""Admission path trust zone resolution tests."""

from __future__ import annotations

import pytest

from app.config.deploy_mode import get_deploy_mode
from app.config.settings import settings
from app.core.security.auth.identity import resolve_identity_from_http_scope
from app.remote_access.trust_zone import (
    AdmissionPath,
    TrustZone,
    admission_path_to_trust_zone,
    resolve_admission_path,
)
from app.services.webui import admin_store
from app.services.webui.passwords import hash_password
from app.services.webui.protection_store import set_password_protection_enabled


@pytest.fixture(autouse=True)
def _local_protected_admin(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEPLOY_MODE", "local")
    monkeypatch.setenv("WEBUI_MODE", "true")
    monkeypatch.setenv("WEBUI_REMOTE_MODE", "true")
    monkeypatch.setattr(settings.database, "state_dir", str(tmp_path))
    get_deploy_mode.cache_clear()
    from app.platform_utils.deployment_capabilities import _reset_capabilities_cache_for_testing

    _reset_capabilities_cache_for_testing()
    admin_store.save_admin("admin", hash_password("Str0ng!Pass"))
    set_password_protection_enabled(True)
    yield
    get_deploy_mode.cache_clear()
    _reset_capabilities_cache_for_testing()


def test_resolve_admission_path_loopback_direct() -> None:
    path = resolve_admission_path(
        path="/api/v1/agents",
        client_ip="127.0.0.1",
        host_header="127.0.0.1:8080",
        headers={},
    )
    assert path == AdmissionPath.LOOPBACK_DIRECT
    assert admission_path_to_trust_zone(path) == TrustZone.LOCAL_TRUSTED


def test_resolve_admission_path_lan_direct() -> None:
    path = resolve_admission_path(
        path="/api/v1/agents",
        client_ip="192.168.1.20",
        host_header="192.168.1.5:8080",
        headers={},
    )
    assert path == AdmissionPath.LAN_DIRECT


def test_resolve_admission_path_public_ingress_via_host() -> None:
    path = resolve_admission_path(
        path="/api/v1/agents",
        client_ip="127.0.0.1",
        host_header="abc.trycloudflare.com",
        headers={},
    )
    assert path == AdmissionPath.PUBLIC_INGRESS
    assert admission_path_to_trust_zone(path) == TrustZone.REMOTE_EXPOSED


def test_resolve_admission_path_public_ingress_via_tunnel_headers() -> None:
    path = resolve_admission_path(
        path="/api/v1/agents",
        client_ip="127.0.0.1",
        host_header="127.0.0.1:8080",
        headers={"Cf-Connecting-Ip": "203.0.113.10"},
    )
    assert path == AdmissionPath.PUBLIC_INGRESS


def test_resolve_admission_path_loopback_with_nextjs_dev_proxy_headers() -> None:
    path = resolve_admission_path(
        path="/api/v1/config",
        client_ip="127.0.0.1",
        host_header="127.0.0.1:8080",
        headers={"X-Forwarded-Host": "localhost:3000", "X-Forwarded-Proto": "http"},
    )
    assert path == AdmissionPath.LOOPBACK_DIRECT
    assert admission_path_to_trust_zone(path) == TrustZone.LOCAL_TRUSTED


def test_resolve_admission_path_public_ingress_matches_configured_url() -> None:
    path = resolve_admission_path(
        path="/api/v1/agents",
        client_ip="127.0.0.1",
        host_header="tunnel.example.com",
        headers={},
        public_ingress_base_url="https://tunnel.example.com",
    )
    assert path == AdmissionPath.PUBLIC_INGRESS


def test_cf_tunnel_loopback_client_denied_without_session() -> None:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/agents",
        "client": ("127.0.0.1", 54321),
        "headers": [(b"host", b"abc.trycloudflare.com")],
    }
    identity = resolve_identity_from_http_scope(scope)
    assert identity.admission_path == AdmissionPath.PUBLIC_INGRESS.value
    assert identity.trust_zone == TrustZone.REMOTE_EXPOSED.value
    assert identity.local_trusted is False
    assert identity.user_id is None


def test_loopback_direct_still_trusted_without_session_when_unprotected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_password_protection_enabled(False)
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/agents",
        "client": ("127.0.0.1", 54321),
        "headers": [(b"host", b"127.0.0.1:8080")],
    }
    identity = resolve_identity_from_http_scope(scope)
    assert identity.admission_path == AdmissionPath.LOOPBACK_DIRECT.value
    assert identity.user_id == "local-user"
