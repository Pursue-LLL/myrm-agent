"""Unit tests for the React E2E bridge timeout diagnostics."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from tests.support.chrome_mcp_e2e import bridge_diagnostics, wait_for_react_e2e_bridge
from tests.support.chrome_mcp_e2e.patching import patch_everywhere


def test_failure_diagnostics_returns_snapshot_dict() -> None:
    client = MagicMock()
    client.evaluate.return_value = {"readyState": "loading", "scriptsPending": 12, "pageErrors": ["error: boom"]}

    result = bridge_diagnostics._bridge_failure_diagnostics(client, MagicMock())

    assert result == {"readyState": "loading", "scriptsPending": 12, "pageErrors": ["error: boom"]}
    assert client.evaluate.call_args.args[1] is bridge_diagnostics._BRIDGE_DIAG_SNAPSHOT_JS


def test_failure_diagnostics_never_masks_original_timeout() -> None:
    client = MagicMock()
    client.evaluate.side_effect = RuntimeError("CDP session closed")

    result = bridge_diagnostics._bridge_failure_diagnostics(client, MagicMock())

    assert result == {"diagnosticsError": "RuntimeError: CDP session closed"}


def test_bridge_timeout_message_carries_page_diagnostics(monkeypatch: pytest.MonkeyPatch) -> None:
    client = MagicMock()
    client.evaluate.return_value = {"ready": False, "bodyLength": 500, "href": "http://127.0.0.1:3000/x"}
    patch_everywhere(monkeypatch, "touch_wall_progress", lambda **_: None)
    patch_everywhere(monkeypatch, "_react_bridge_wait_timeout_sec", lambda _t: 0.0)
    patch_everywhere(monkeypatch, "_bridge_failure_diagnostics", lambda *_: {"scriptsPending": 3})

    with pytest.raises(AssertionError, match=r"diagnostics=\{'scriptsPending': 3\}"):
        wait_for_react_e2e_bridge(client, MagicMock(), timeout_sec=0.0)


def test_bridge_wait_state_is_emitted_to_stderr(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    patch_everywhere(monkeypatch, "_bridge_failure_diagnostics", lambda *_: {"scriptsPending": 7})

    bridge_diagnostics._log_bridge_wait_state(MagicMock(), MagicMock(), polls=4, reload_passes=1, last={"bodyLength": 0})

    err = capsys.readouterr().err
    assert "E2E_BRIDGE_WAIT: polls=4 reload_passes=1" in err
    assert "'scriptsPending': 7" in err
