"""Unit smoke tests for desktop approval trust selector helpers."""

from __future__ import annotations

import json

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
