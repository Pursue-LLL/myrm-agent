"""Host allowlist tests for remote access."""

from __future__ import annotations

from app.middleware.host_allowlist import build_allowed_hosts, is_allowed_host


def test_build_allowed_hosts_includes_ingress_and_tunnel() -> None:
    allowed = build_allowed_hosts(
        "https://tunnel.example.com",
        tunnel_public_url="https://abc.trycloudflare.com",
    )
    assert "tunnel.example.com" in allowed
    assert "abc.trycloudflare.com" in allowed
    assert "127.0.0.1" in allowed


def test_is_allowed_host_accepts_loopback_and_lan() -> None:
    allowed = build_allowed_hosts("")
    assert is_allowed_host("127.0.0.1:8080", allowed)
    assert is_allowed_host("192.168.1.10:8080", allowed)


def test_is_allowed_host_rejects_unlisted_public_host() -> None:
    allowed = build_allowed_hosts("https://tunnel.example.com")
    assert not is_allowed_host("evil.example.org", allowed)


def test_is_allowed_host_accepts_configured_tunnel_host() -> None:
    allowed = build_allowed_hosts("", tunnel_public_url="https://abc.trycloudflare.com")
    assert is_allowed_host("abc.trycloudflare.com", allowed)
