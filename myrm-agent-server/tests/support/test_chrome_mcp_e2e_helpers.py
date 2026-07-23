"""Unit tests for chrome_mcp_e2e helper utilities."""

from __future__ import annotations

import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tests.support.chrome_mcp_e2e import wait_for_state, warm_ui_route


def test_open_mcp_page_reapplies_shpoib_binding_after_reload() -> None:
    source = Path(__file__).with_name("chrome_mcp_e2e.py").read_text(encoding="utf-8")
    block = source.split("def open_mcp_page", 1)[1].split("\ndef ", 1)[0]
    assert "client.reload" in block
    assert "_reapply_shpoib_runtime_after_reload" in block
    assert block.index("reload") < block.index("_reapply_shpoib_runtime_after_reload")


def test_wait_for_state_parses_json_string_ready() -> None:
    client = MagicMock()
    page = MagicMock()
    client.evaluate.return_value = '{"ready": true, "text": "ok"}'

    result = wait_for_state(client, page, "(() => ({}))()", timeout_sec=1.0)

    assert result["ready"] is True
    assert result["text"] == "ok"


def test_warm_ui_route_retries_until_shared_ui_recovers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MYRM_CHROME_E2E_SHARED_UI_WAIT_SEC", "5")
    monkeypatch.setenv("MYRM_CHROME_E2E_SHARED_UI_POLL_SEC", "0.01")
    attempts = {"count": 0}

    class _FakeResponse:
        status = 200

        def __enter__(self) -> _FakeResponse:
            return self

        def __exit__(self, *args: object) -> None:
            return None

    def _urlopen(request: object, timeout: float = 30.0) -> _FakeResponse:
        del request, timeout
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise urllib.error.URLError("connection refused")
        return _FakeResponse()

    with patch(
        "tests.support.chrome_mcp_e2e.get_e2e_ui_url",
        return_value="http://127.0.0.1:3000",
    ):
        with patch("urllib.request.urlopen", side_effect=_urlopen):
            warm_ui_route("/")
    assert attempts["count"] == 3
