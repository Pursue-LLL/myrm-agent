#!/usr/bin/env python3
"""Readonly Google Workspace API helper for the google-workspace prebuilt skill.

Uses GOOGLE_WORKSPACE_TOKEN from the environment (injected by bash/safe_exec).
MYRM_USER_TIMEZONE (or TZ) selects the calendar day boundary; defaults to UTC.
Stdlib only — no extra dependencies in agent bash sessions.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo


def _require_token() -> str:
    token = os.environ.get("GOOGLE_WORKSPACE_TOKEN", "").strip()
    if not token:
        _fail("GOOGLE_WORKSPACE_TOKEN is not set")
    return token


def _fail(message: str, *, code: int = 1) -> None:
    print(json.dumps({"error": message}))
    sys.exit(code)


def _http_get(url: str, token: str) -> dict[str, object]:
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = response.read().decode()
            parsed = json.loads(payload)
            return parsed if isinstance(parsed, dict) else {"data": parsed}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:500]
        _fail(f"HTTP {exc.code}: {detail}")
    except urllib.error.URLError as exc:
        _fail(f"Network error: {exc.reason}")


def _resolve_timezone() -> ZoneInfo:
    for key in ("MYRM_USER_TIMEZONE", "TZ"):
        raw = os.environ.get(key, "").strip()
        if not raw:
            continue
        try:
            return ZoneInfo(raw)
        except Exception:
            continue
    return ZoneInfo("UTC")


def _format_rfc3339(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.isoformat()


def _local_day_bounds(tz: ZoneInfo | None = None) -> tuple[str, str]:
    zone = tz or _resolve_timezone()
    now = datetime.now(zone)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1) - timedelta(microseconds=1)
    return _format_rfc3339(start), _format_rfc3339(end)


def calendar_today(token: str, *, tz: ZoneInfo | None = None) -> dict[str, object]:
    time_min, time_max = _local_day_bounds(tz)
    params = urllib.parse.urlencode(
        {
            "singleEvents": "true",
            "orderBy": "startTime",
            "timeMin": time_min,
            "timeMax": time_max,
            "maxResults": "25",
        }
    )
    url = f"https://www.googleapis.com/calendar/v3/calendars/primary/events?{params}"
    return _http_get(url, token)


def _header_value(headers: object, name: str) -> str | None:
    if not isinstance(headers, list):
        return None
    for header in headers:
        if isinstance(header, dict) and header.get("name") == name:
            value = header.get("value")
            return str(value) if value is not None else None
    return None


def _gmail_message_summary(token: str, message_id: str) -> dict[str, object]:
    query = urllib.parse.urlencode(
        [
            ("format", "metadata"),
            ("metadataHeaders", "Subject"),
            ("metadataHeaders", "From"),
        ],
        doseq=True,
    )
    encoded_id = urllib.parse.quote(message_id, safe="")
    url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{encoded_id}?{query}"
    data = _http_get(url, token)
    payload = data.get("payload")
    headers = payload.get("headers") if isinstance(payload, dict) else None
    return {
        "id": data.get("id", message_id),
        "threadId": data.get("threadId"),
        "snippet": data.get("snippet"),
        "subject": _header_value(headers, "Subject"),
        "from": _header_value(headers, "From"),
        "internalDate": data.get("internalDate"),
    }


def gmail_inbox(token: str, *, max_results: int = 10) -> dict[str, object]:
    params = urllib.parse.urlencode(
        {
            "maxResults": str(max_results),
            "labelIds": "INBOX",
        }
    )
    list_url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages?{params}"
    list_data = _http_get(list_url, token)
    raw_messages = list_data.get("messages")
    if not isinstance(raw_messages, list):
        return list_data

    summaries: list[dict[str, object]] = []
    for item in raw_messages[:max_results]:
        if not isinstance(item, dict):
            continue
        message_id = item.get("id")
        if not isinstance(message_id, str) or not message_id:
            continue
        summaries.append(_gmail_message_summary(token, message_id))

    return {
        "messages": summaries,
        "resultSizeEstimate": list_data.get("resultSizeEstimate"),
    }


def drive_recent(token: str, *, page_size: int = 10) -> dict[str, object]:
    params = urllib.parse.urlencode(
        {
            "pageSize": str(page_size),
            "orderBy": "modifiedTime desc",
            "fields": "files(id,name,mimeType,modifiedTime)",
        }
    )
    url = f"https://www.googleapis.com/drive/v3/files?{params}"
    return _http_get(url, token)


def main() -> None:
    parser = argparse.ArgumentParser(description="Google Workspace readonly API helper")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("calendar-today", help="List primary calendar events for today (user timezone)")
    sub.add_parser("gmail-inbox", help="List recent INBOX messages with subject, from, snippet")
    sub.add_parser("drive-recent", help="List recently modified Drive files")

    args = parser.parse_args()
    token = _require_token()

    if args.command == "calendar-today":
        result = calendar_today(token)
    elif args.command == "gmail-inbox":
        result = gmail_inbox(token)
    else:
        result = drive_recent(token)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
