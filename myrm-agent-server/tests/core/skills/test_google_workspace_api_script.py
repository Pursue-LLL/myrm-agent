"""Tests for google-workspace prebuilt skill API helper script."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

SCRIPT_PATH = (
    Path(__file__).resolve().parents[3]
    / "assets"
    / "prebuilt_skills"
    / "google-workspace"
    / "scripts"
    / "google_api.py"
)


@pytest.fixture
def google_api_module():
    spec = importlib.util.spec_from_file_location("google_api", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestGoogleApiCalendarToday:
    def test_calendar_today_parses_response(self, google_api_module) -> None:
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(
            {
                "items": [
                    {
                        "summary": "Standup",
                        "start": {"dateTime": "2026-06-25T09:00:00Z"},
                    }
                ]
            }
        ).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=None)

        with patch.object(google_api_module.urllib.request, "urlopen", return_value=mock_response):
            result = google_api_module.calendar_today("test-access-token")

        assert "items" in result
        items = result["items"]
        assert isinstance(items, list)
        assert items[0]["summary"] == "Standup"

    def test_calendar_today_http_error_exits(self, google_api_module) -> None:
        import urllib.error

        error = urllib.error.HTTPError(
            url="https://example.com",
            code=401,
            msg="Unauthorized",
            hdrs=None,
            fp=MagicMock(read=MagicMock(return_value=b'{"error":"invalid_token"}')),
        )

        with (
            patch.object(google_api_module.urllib.request, "urlopen", side_effect=error),
            pytest.raises(SystemExit) as exc,
        ):
            google_api_module.calendar_today("bad-token")

        assert exc.value.code == 1


class TestGoogleApiGmailInbox:
    def test_gmail_inbox_enriches_message_metadata(self, google_api_module) -> None:
        list_response = MagicMock()
        list_response.read.return_value = json.dumps(
            {
                "messages": [{"id": "msg-1", "threadId": "thread-1"}],
                "resultSizeEstimate": 1,
            }
        ).encode()
        list_response.__enter__ = MagicMock(return_value=list_response)
        list_response.__exit__ = MagicMock(return_value=None)

        detail_response = MagicMock()
        detail_response.read.return_value = json.dumps(
            {
                "id": "msg-1",
                "threadId": "thread-1",
                "snippet": "Hello there",
                "internalDate": "1719300000000",
                "payload": {
                    "headers": [
                        {"name": "Subject", "value": "Weekly update"},
                        {"name": "From", "value": "team@example.com"},
                    ]
                },
            }
        ).encode()
        detail_response.__enter__ = MagicMock(return_value=detail_response)
        detail_response.__exit__ = MagicMock(return_value=None)

        with patch.object(
            google_api_module.urllib.request,
            "urlopen",
            side_effect=[list_response, detail_response],
        ):
            result = google_api_module.gmail_inbox("test-access-token", max_results=5)

        messages = result["messages"]
        assert isinstance(messages, list)
        assert len(messages) == 1
        assert messages[0]["subject"] == "Weekly update"
        assert messages[0]["from"] == "team@example.com"
        assert messages[0]["snippet"] == "Hello there"
