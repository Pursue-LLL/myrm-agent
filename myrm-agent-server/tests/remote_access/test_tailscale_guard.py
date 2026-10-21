"""Unit and integration tests for Tailscale Zero-Trust Remote Access Guard Suite."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.core.security.auth.identity import (
    is_tailscale_ip,
    resolve_identity,
)
from app.middleware.host_allowlist import build_allowed_hosts, is_allowed_host
from app.remote_access.tailscale_service import (
    TailscaleNodeInfo,
    clear_tailscale_cache_for_testing,
    parse_tailscale_status_json,
    probe_tailscale_status,
)
from app.remote_access.trust_zone import (
    AdmissionPath,
    TrustZone,
    admission_path_to_trust_zone,
    is_public_host,
    resolve_admission_path,
)


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    clear_tailscale_cache_for_testing()
    yield
    clear_tailscale_cache_for_testing()


def test_is_tailscale_ip_ipv4_cgnat() -> None:
    # RFC 6598: 100.64.0.0/10 (100.64.0.0 - 100.127.255.255)
    assert is_tailscale_ip("100.64.0.1")
    assert is_tailscale_ip("100.100.100.100")
    assert is_tailscale_ip("100.127.255.254")

    # Outside the 100.64.0.0/10 block
    assert not is_tailscale_ip("100.63.255.255")
    assert not is_tailscale_ip("100.128.0.1")
    assert not is_tailscale_ip("192.168.1.1")
    assert not is_tailscale_ip("127.0.0.1")
    assert not is_tailscale_ip("8.8.8.8")
    assert not is_tailscale_ip("")
    assert not is_tailscale_ip("invalid-ip")


def test_is_tailscale_ip_ipv6_ula() -> None:
    # Tailscale IPv6 ULA: fd7a:115c:a1e0::/48
    assert is_tailscale_ip("fd7a:115c:a1e0::1")
    assert is_tailscale_ip("fd7a:115c:a1e0:ab12:34cd:56ef:7890:1234")

    # Outside the fd7a:115c:a1e0::/48 prefix
    assert not is_tailscale_ip("fd7a:115c:a1e1::1")
    assert not is_tailscale_ip("2001:db8::1")
    assert not is_tailscale_ip("::1")


def test_resolve_admission_path_tailscale_peer_ip() -> None:
    path = resolve_admission_path(
        path="/api/v1/agents",
        client_ip="100.101.102.103",
        host_header="100.101.102.103:8000",
        headers={},
    )
    assert path == AdmissionPath.TAILSCALE_DIRECT
    assert admission_path_to_trust_zone(path) == TrustZone.LOCAL_TRUSTED


def test_resolve_admission_path_tailscale_serve_magicdns_proxy() -> None:
    # Tailscale Serve terminates at loopback with MagicDNS domain in Host header
    path = resolve_admission_path(
        path="/api/v1/agents",
        client_ip="127.0.0.1",
        host_header="my-mac.shark-fin.ts.net:8000",
        headers={},
    )
    assert path == AdmissionPath.TAILSCALE_DIRECT
    assert admission_path_to_trust_zone(path) == TrustZone.LOCAL_TRUSTED


def test_is_public_host_tailscale_exclusions() -> None:
    # Tailscale IP and MagicDNS domain are not treated as public exposure
    assert not is_public_host("100.101.102.103:8000")
    assert not is_public_host("[fd7a:115c:a1e0::1]:8000")
    assert not is_public_host("my-node.ts.net")
    assert not is_public_host("my-node.shark-fin.ts.net:443")

    # Regular public hosts are still flagged as public
    assert is_public_host("example.com")
    assert is_public_host("8.8.8.8:8000")


def test_is_allowed_host_tailscale() -> None:
    allowed = build_allowed_hosts("")
    assert is_allowed_host("my-mac.ts.net", allowed)
    assert is_allowed_host("my-mac.shark-fin.ts.net:8000", allowed)
    assert is_allowed_host("100.101.102.103:8000", allowed)
    assert is_allowed_host("[fd7a:115c:a1e0::1]:8000", allowed)
    assert not is_allowed_host("evil.com", allowed)
    assert not is_allowed_host("8.8.8.8:8000", allowed)


def test_tailscale_user_header_anti_spoofing() -> None:
    # 1. Attacker sends forged Tailscale-User-Login from public IP: MUST BE IGNORED
    spoofed_identity = resolve_identity(
        path="/api/v1/agents",
        method="GET",
        headers={"Tailscale-User-Login": "admin@example.com"},
        client_ip="8.8.8.8",
    )
    assert spoofed_identity.tailscale_user is None

    # 2. Legitimate request from Tailscale IP: ACCEPTED
    legit_ts_identity = resolve_identity(
        path="/api/v1/agents",
        method="GET",
        headers={"Tailscale-User-Login": "alice@example.com"},
        client_ip="100.101.102.103",
    )
    assert legit_ts_identity.tailscale_user == "alice@example.com"

    # 3. Legitimate request from Tailscale Serve (loopback): ACCEPTED
    legit_serve_identity = resolve_identity(
        path="/api/v1/agents",
        method="GET",
        headers={
            "Host": "my-mac.shark-fin.ts.net",
            "Tailscale-User-Login": "bob@example.com",
        },
        client_ip="127.0.0.1",
    )
    assert legit_serve_identity.tailscale_user == "bob@example.com"


def test_parse_tailscale_status_json_success() -> None:
    mock_payload = {
        "BackendState": "Running",
        "Self": {
            "ID": "node-12345",
            "HostName": "my-dev-box",
            "DNSName": "my-dev-box.shark-fin.ts.net.",
            "TailscaleIPs": ["100.101.102.103", "fd7a:115c:a1e0::1"],
            "UserID": 1001,
        },
        "User": {
            "1001": {
                "LoginName": "dev@company.com",
                "DisplayName": "Dev User",
            }
        },
    }
    # When serve is NOT active: serve_url is None to avoid dead links
    info_no_serve = parse_tailscale_status_json(json.dumps(mock_payload), serve_active=False)
    assert info_no_serve.installed is True
    assert info_no_serve.running is True
    assert info_no_serve.ips == ("100.101.102.103", "fd7a:115c:a1e0::1")
    assert info_no_serve.fqdn == "my-dev-box.shark-fin.ts.net"
    assert info_no_serve.node_name == "my-dev-box"
    assert info_no_serve.tailnet == "shark-fin"
    assert info_no_serve.user == "dev@company.com"
    assert info_no_serve.serve_url is None

    # When serve IS active: serve_url is populated with verified HTTPS URL
    info_with_serve = parse_tailscale_status_json(json.dumps(mock_payload), serve_active=True)
    assert info_with_serve.serve_url == "https://my-dev-box.shark-fin.ts.net"


def test_parse_tailscale_serve_status_json() -> None:
    from app.remote_access.tailscale_service import parse_tailscale_serve_status_json

    # Active web handlers configured
    active_payload = {
        "TCP": {"443": {"HTTPS": True}},
        "Web": {"my-mac.ts.net:443": {"Handlers": {"/": {"Proxy": "http://127.0.0.1:8000"}}}},
    }
    assert parse_tailscale_serve_status_json(json.dumps(active_payload)) is True

    # Inactive / empty serve status
    assert parse_tailscale_serve_status_json("{}") is False
    assert parse_tailscale_serve_status_json("not json") is False


def test_parse_tailscale_status_json_invalid() -> None:
    info = parse_tailscale_status_json("not valid json")
    assert info.installed is True
    assert info.running is False
    assert info.ips == ()
    assert info.fqdn is None


@pytest.mark.asyncio
async def test_probe_tailscale_status_cached() -> None:
    mock_info = TailscaleNodeInfo(
        installed=True,
        running=True,
        ips=("100.64.1.2",),
        fqdn="box.ts.net",
        node_name="box",
        tailnet=None,
        user="test@ts.net",
        serve_url="https://box.ts.net",
    )
    mock_proc = AsyncMock()
    mock_proc.returncode = 0
    mock_proc.communicate.return_value = (b'{"BackendState":"Running"}', b"")

    with patch(
        "app.remote_access.tailscale_service.find_tailscale_binary",
        return_value="/usr/bin/tailscale",
    ), patch(
        "asyncio.create_subprocess_exec",
        return_value=mock_proc,
    ), patch(
        "app.remote_access.tailscale_service.parse_tailscale_status_json",
        return_value=mock_info,
    ):
        first = await probe_tailscale_status(cache_ttl_seconds=10.0, use_cache=False)
        assert first.running is True
        assert first.node_name == "box"

        # Subsequent call with use_cache=True should use cache
        cached = await probe_tailscale_status(cache_ttl_seconds=10.0, use_cache=True)
        assert cached == first


@pytest.mark.asyncio
async def test_tailscale_status_endpoint() -> None:
    from app.api.remote_access.router import tailscale_status

    response = await tailscale_status()
    payload = json.loads(response.body)
    assert payload["success"] is True
    assert "data" in payload
    data = payload["data"]
    assert "installed" in data
    assert "running" in data
    assert "ips" in data
