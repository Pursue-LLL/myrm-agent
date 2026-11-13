"""Tests for google-workspace prebuilt skill API helper script."""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

SCRIPT_PATH = (
    Path(__file__).resolve().parents[3] / "assets" / "prebuilt_skills" / "google-workspace" / "scripts" / "google_api.py"
)
_RANGE_BOUNDS = {"time_min": "2026-06-25T00:00:00+08:00", "time_max": "2026-06-25T23:59:59+08:00"}


def _json_response(payload: dict[str, object]) -> MagicMock:
    response = MagicMock()
    response.read.return_value = json.dumps(payload).encode()
    response.__enter__ = MagicMock(return_value=response)
    response.__exit__ = MagicMock(return_value=None)
    return response


def _event(event_id: str, start: str, end: str) -> dict[str, object]:
    return {"id": event_id, "summary": event_id.title(), "start": {"dateTime": start}, "end": {"dateTime": end}}


@pytest.fixture
def google_api_module(monkeypatch: pytest.MonkeyPatch):
    # A staged script finds its sibling modules because its own directory leads sys.path.
    monkeypatch.syspath_prepend(str(SCRIPT_PATH.parent))
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

    def test_calendar_today_uses_user_timezone_day_bounds(self, google_api_module, monkeypatch) -> None:
        fixed_now = datetime(2026, 6, 25, 10, 30, tzinfo=ZoneInfo("Asia/Shanghai"))
        monkeypatch.setenv("MYRM_USER_TIMEZONE", "Asia/Shanghai")

        captured_url: list[str] = []

        def fake_urlopen(request: object, timeout: int = 30) -> MagicMock:
            _ = timeout
            captured_url.append(getattr(request, "full_url", str(request)))
            mock_response = MagicMock()
            mock_response.read.return_value = json.dumps({"items": []}).encode()
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=None)
            return mock_response

        with (
            patch.object(google_api_module, "datetime") as mock_datetime,
            patch.object(google_api_module.urllib.request, "urlopen", side_effect=fake_urlopen),
        ):
            mock_datetime.now.return_value = fixed_now
            google_api_module.calendar_today("test-access-token")

        assert captured_url
        url = captured_url[0]
        assert "timeMin=2026-06-25T00%3A00%3A00%2B08%3A00" in url
        assert "timeMax=2026-06-25T23%3A59%3A59.999999%2B08%3A00" in url


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


class TestGoogleApiWriteCommands:
    def test_gmail_send_posts_to_api(self, google_api_module) -> None:
        send_response = MagicMock()
        send_response.read.return_value = json.dumps({"id": "sent-1", "threadId": "thread-1"}).encode()
        send_response.__enter__ = MagicMock(return_value=send_response)
        send_response.__exit__ = MagicMock(return_value=None)

        with patch.object(google_api_module.urllib.request, "urlopen", return_value=send_response) as mock_open:
            result = google_api_module.gmail_send(
                "token",
                to="user@example.com",
                subject="Hello",
                body="Body",
            )

        assert result["status"] == "sent"
        assert result["id"] == "sent-1"
        request = mock_open.call_args[0][0]
        assert request.full_url.endswith("/messages/send")
        assert request.method == "POST"

    def test_gmail_inbox_empty_inbox_returns_empty_messages(self, google_api_module) -> None:
        list_response = MagicMock()
        list_response.read.return_value = json.dumps({"messages": [], "resultSizeEstimate": 0}).encode()
        list_response.__enter__ = MagicMock(return_value=list_response)
        list_response.__exit__ = MagicMock(return_value=None)

        with patch.object(google_api_module.urllib.request, "urlopen", return_value=list_response):
            result = google_api_module.gmail_inbox("test-access-token")

        messages = result["messages"]
        assert isinstance(messages, list)
        assert messages == []


class TestGoogleApiCalendarPagination:
    """A calendar query reads every page it is allowed to and says when it stopped short."""

    def test_reads_every_page_until_the_token_runs_out(self, google_api_module) -> None:
        events = [
            _event("a", "2026-06-25T09:00:00+08:00", "2026-06-25T09:30:00+08:00"),
            _event("b", "2026-06-25T10:00:00+08:00", "2026-06-25T10:30:00+08:00"),
            _event("c", "2026-06-25T11:00:00+08:00", "2026-06-25T11:30:00+08:00"),
            _event("d", "2026-06-25T12:00:00+08:00", "2026-06-25T12:30:00+08:00"),
        ]
        pages = [
            _json_response({"items": events[:2], "nextPageToken": "t1"}),
            _json_response({"items": events[2:3], "nextPageToken": "t2"}),
            _json_response({"items": events[3:]}),
        ]

        with patch.object(google_api_module.urllib.request, "urlopen", side_effect=pages) as mock_open:
            result = google_api_module.calendar_range("token", **_RANGE_BOUNDS)

        assert result["items"] == events
        assert result["truncated"] is False
        assert result["conflicts"] == []
        queries = [urllib.parse.parse_qs(urllib.parse.urlsplit(call.args[0].full_url).query) for call in mock_open.call_args_list]
        assert [query.get("pageToken") for query in queries] == [None, ["t1"], ["t2"]]
        assert all(query["maxResults"] == ["50"] for query in queries)

    @pytest.mark.parametrize("empty_page", [{"items": []}, {}], ids=["empty-items", "no-items-key"])
    def test_follows_a_token_past_an_empty_page(self, google_api_module, empty_page: dict[str, object]) -> None:
        early = _event("early", "2026-06-25T09:00:00+08:00", "2026-06-25T09:30:00+08:00")
        late = _event("late", "2026-06-25T15:00:00+08:00", "2026-06-25T15:30:00+08:00")
        pages = [
            _json_response({"items": [early], "nextPageToken": "t1"}),
            _json_response({**empty_page, "nextPageToken": "t2"}),
            _json_response({"items": [late]}),
        ]

        with patch.object(google_api_module.urllib.request, "urlopen", side_effect=pages) as mock_open:
            result = google_api_module.calendar_range("token", **_RANGE_BOUNDS)

        assert result["items"] == [early, late]
        assert result["truncated"] is False
        assert mock_open.call_count == 3

    def test_stops_at_the_page_cap_and_reports_truncation(self, google_api_module) -> None:
        cap = google_api_module._MAX_EVENT_PAGES
        event = _event("busy", "2026-06-25T09:00:00+08:00", "2026-06-25T09:30:00+08:00")

        with patch.object(
            google_api_module.urllib.request,
            "urlopen",
            side_effect=lambda *_args, **_kwargs: _json_response({"items": [event], "nextPageToken": "more"}),
        ) as mock_open:
            result = google_api_module.calendar_range("token", **_RANGE_BOUNDS)

        assert mock_open.call_count == cap
        assert result["truncated"] is True
        assert result["items"] == [event] * cap
        assert "nextPageToken" not in result

    def test_a_range_ending_on_the_last_allowed_page_is_complete(self, google_api_module) -> None:
        cap = google_api_module._MAX_EVENT_PAGES
        event = _event("busy", "2026-06-25T09:00:00+08:00", "2026-06-25T09:30:00+08:00")
        pages = [_json_response({"items": [event], "nextPageToken": f"t{n}"}) for n in range(cap - 1)]
        pages.append(_json_response({"items": [event]}))

        with patch.object(google_api_module.urllib.request, "urlopen", side_effect=pages) as mock_open:
            result = google_api_module.calendar_range("token", **_RANGE_BOUNDS)

        assert mock_open.call_count == cap
        assert result["truncated"] is False

    def test_finds_conflicts_across_a_page_boundary(self, google_api_module) -> None:
        early = _event("early", "2026-06-25T09:00:00+08:00", "2026-06-25T10:00:00+08:00")
        overlapping = _event("overlapping", "2026-06-25T09:30:00+08:00", "2026-06-25T10:30:00+08:00")
        pages = [
            _json_response({"items": [early], "nextPageToken": "t1"}),
            _json_response({"items": [overlapping]}),
        ]

        with patch.object(google_api_module.urllib.request, "urlopen", side_effect=pages):
            result = google_api_module.calendar_range("token", **_RANGE_BOUNDS)

        assert [(pair["first"]["id"], pair["second"]["id"]) for pair in result["conflicts"]] == [("early", "overlapping")]

    def test_keeps_raw_events_and_metadata_with_the_verdict_fields_first(self, google_api_module) -> None:
        event = {
            **_event("raw", "2026-06-25T09:00:00+08:00", "2026-06-25T09:30:00+08:00"),
            "attendees": [{"email": "me@example.com", "self": True, "responseStatus": "accepted"}],
        }
        response = {"kind": "calendar#events", "summary": "Primary", "timeZone": "Asia/Shanghai", "items": [event]}

        with patch.object(google_api_module.urllib.request, "urlopen", return_value=_json_response(response)):
            result = google_api_module.calendar_range("token", **_RANGE_BOUNDS)

        assert result["items"] == [event]
        assert (result["kind"], result["summary"], result["timeZone"]) == ("calendar#events", "Primary", "Asia/Shanghai")
        # An oversized output loses its middle, so the verdict leads and the event list closes the object.
        assert list(result)[:2] == ["truncated", "conflicts"]
        assert list(result)[-1] == "items"

    def test_a_failing_later_page_fails_the_whole_call(self, google_api_module, capsys) -> None:
        error = urllib.error.HTTPError(
            url="https://example.com",
            code=500,
            msg="Server Error",
            hdrs=None,
            fp=MagicMock(read=MagicMock(return_value=b"upstream failure")),
        )
        first_page = _json_response(
            {
                "items": [_event("a", "2026-06-25T09:00:00+08:00", "2026-06-25T09:30:00+08:00")],
                "nextPageToken": "t1",
            }
        )

        with (
            patch.object(google_api_module.urllib.request, "urlopen", side_effect=[first_page, error]),
            pytest.raises(SystemExit) as exc,
        ):
            google_api_module.calendar_range("token", **_RANGE_BOUNDS)

        assert exc.value.code == 1
        assert json.loads(capsys.readouterr().out)["error"].startswith("HTTP 500")

    @pytest.mark.parametrize(
        "command",
        [["calendar-today"], ["calendar-range", "--time-min", "2026-06-25T00:00:00Z", "--time-max", "2026-06-26T00:00:00Z"]],
        ids=["calendar-today", "calendar-range"],
    )
    def test_the_calendar_commands_print_the_verdict_fields(
        self, google_api_module, monkeypatch, capsys, command: list[str]
    ) -> None:
        events = [
            _event("standup", "2026-06-25T09:00:00+08:00", "2026-06-25T10:00:00+08:00"),
            _event("review", "2026-06-25T09:30:00+08:00", "2026-06-25T10:30:00+08:00"),
        ]
        monkeypatch.setenv("GOOGLE_WORKSPACE_TOKEN", "token")
        monkeypatch.setattr(sys, "argv", ["google_api.py", *command])

        with patch.object(google_api_module.urllib.request, "urlopen", return_value=_json_response({"items": events})):
            google_api_module.main()

        printed = json.loads(capsys.readouterr().out)
        assert printed["truncated"] is False
        assert [(pair["first"]["id"], pair["second"]["id"]) for pair in printed["conflicts"]] == [("standup", "review")]
        assert printed["items"] == events


def test_the_script_runs_from_a_copy_of_its_skill_directory(tmp_path: Path) -> None:
    """The staged skill is run as `python3 scripts/google_api.py`; its sibling module must resolve from there."""
    staged = tmp_path / "google-workspace"
    shutil.copytree(SCRIPT_PATH.parents[1], staged, ignore=shutil.ignore_patterns("__pycache__"))

    completed = subprocess.run(
        [sys.executable, "scripts/google_api.py", "--help"],
        cwd=staged,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "calendar-range" in completed.stdout
