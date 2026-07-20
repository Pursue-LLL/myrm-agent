"""Unit tests for chrome_mcp_e2e helper utilities."""

from __future__ import annotations

from unittest.mock import MagicMock

from tests.support.chrome_mcp_e2e import wait_for_state


def test_wait_for_state_parses_json_string_ready() -> None:
    client = MagicMock()
    page = MagicMock()
    client.evaluate.return_value = '{"ready": true, "text": "ok"}'

    result = wait_for_state(client, page, "(() => ({}))()", timeout_sec=1.0)

    assert result["ready"] is True
    assert result["text"] == "ok"
