"""Unit tests for the React E2E bridge timeout diagnostics."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from tests.support import chrome_mcp_e2e as support


def test_failure_diagnostics_returns_snapshot_dict() -> None:
    client = MagicMock()
    client.evaluate.return_value = {"readyState": "loading", "scriptsPending": 12, "pageErrors": ["error: boom"]}

    result = support._bridge_failure_diagnostics(client, MagicMock())

    assert result == {"readyState": "loading", "scriptsPending": 12, "pageErrors": ["error: boom"]}
    assert client.evaluate.call_args.args[1] is support._BRIDGE_DIAG_SNAPSHOT_JS


def test_failure_diagnostics_never_masks_original_timeout() -> None:
    client = MagicMock()
    client.evaluate.side_effect = RuntimeError("CDP session closed")

    result = support._bridge_failure_diagnostics(client, MagicMock())

    assert result == {"diagnosticsError": "RuntimeError: CDP session closed"}


def test_bridge_timeout_message_carries_page_diagnostics(monkeypatch: pytest.MonkeyPatch) -> None:
    client = MagicMock()
    client.evaluate.return_value = {"ready": False, "bodyLength": 500, "href": "http://127.0.0.1:3000/x"}
    monkeypatch.setattr(support, "touch_wall_progress", lambda **_: None)
    monkeypatch.setattr(support, "_react_bridge_wait_timeout_sec", lambda _t: 0.0)
    monkeypatch.setattr(support, "_bridge_failure_diagnostics", lambda *_: {"scriptsPending": 3})

    with pytest.raises(AssertionError, match=r"diagnostics=\{'scriptsPending': 3\}"):
        support.wait_for_react_e2e_bridge(client, MagicMock(), timeout_sec=0.0)
