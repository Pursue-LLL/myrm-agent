"""Fixtures for the Feishu SDK document tests."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock

import pytest

from app.channels.providers.feishu.sdk import FeishuClient


@pytest.fixture
def client() -> FeishuClient:
    c = FeishuClient("app", "secret")
    c._token = "tok"
    c._token_expires_at = time.monotonic() + 3600
    mock_http = AsyncMock()
    mock_http.is_closed = False
    c._http = mock_http
    return c
