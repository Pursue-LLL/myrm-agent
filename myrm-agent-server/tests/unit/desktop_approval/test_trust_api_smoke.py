"""Unit smoke tests for desktop approval trust selector helpers."""

from __future__ import annotations

import json

import pytest
from cdp_chat_support import get_e2e_api_url, resolve_e2e_api_base

from tests.e2e.desktop_approval.trust_api import (
    desktop_trust_revoke_selector_js,
    desktop_trust_revoke_testid,
)


def test_desktop_trust_revoke_testid() -> None:
    assert desktop_trust_revoke_testid("com.apple.TextEdit") == "desktop-trust-revoke-com.apple.TextEdit"


def test_desktop_trust_revoke_selector_js_escapes_quotes() -> None:
    trust_key = 'foo"bar\\baz'
    selector = desktop_trust_revoke_selector_js(trust_key)
    expected = json.dumps(f'[data-testid="{desktop_trust_revoke_testid(trust_key)}"]')
    assert selector == expected


def test_resolve_e2e_api_base_rejects_non_loopback() -> None:
    with pytest.raises(RuntimeError, match="loopback HTTP origin"):
        resolve_e2e_api_base("http://evil.example:8080")


def test_get_e2e_api_url_normalizes_loopback_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("E2E_API_BASE", "http://127.0.0.1:19080/")
    assert get_e2e_api_url() == "http://127.0.0.1:19080"


def test_get_e2e_api_url_accepts_local_bind_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("E2E_API_BASE", "http://0.0.0.0:18080/")
    assert get_e2e_api_url() == "http://0.0.0.0:18080"
