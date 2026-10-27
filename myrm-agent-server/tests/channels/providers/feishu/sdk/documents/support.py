"""Shared helpers for the Feishu SDK document tests."""

from __future__ import annotations

from unittest.mock import MagicMock

import httpx


def mock_response(
    status_code: int = 200,
    json_data: dict | None = None,
) -> httpx.Response:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.is_success = 200 <= status_code < 300
    resp.json.return_value = json_data or {}
    return resp
