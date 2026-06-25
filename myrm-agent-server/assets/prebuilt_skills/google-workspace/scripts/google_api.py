#!/usr/bin/env python3
"""Google Workspace API helper for the google-workspace prebuilt skill.

[INPUT]
- Process env GOOGLE_WORKSPACE_TOKEN (injected by LocalExecutor/safe_exec after sanitize)
- Process env MYRM_USER_TIMEZONE or TZ (user-local calendar day boundary)

[OUTPUT]
- JSON on stdout for readonly and write CLI subcommands

[POS]
Vendor skill script staged into workspace by bash_executor; stdlib-only Google REST client.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from email.mime.text import MIMEText
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


def _http_post(url: str, token: str, body: dict[str, object]) -> dict[str, object]:
    data = json.dumps(body).encode()
    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = response.read().decode()
            if not payload.strip():
                return {"status": "ok"}
            parsed = json.loads(payload)
            return parsed if isinstance(parsed, dict) else {"data": parsed}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:500]
        _fail(f"HTTP {exc.code}: {detail}")
    except urllib.error.URLError as exc:
        _fail(f"Network error: {exc.reason}")


def _http_delete(url: str, token: str) -> dict[str, object]:
    request = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {token}"},
        method="DELETE",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            if response.status in (200, 204):
                return {"status": "deleted"}
            payload = response.read().decode()
            if not payload.strip():
                return {"status": "deleted"}
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
    return calendar_range(token, time_min=time_min, time_max=time_max)


def calendar_range(token: str, *, time_min: str, time_max: str) -> dict[str, object]:
    params = urllib.parse.urlencode(
        {
            "singleEvents": "true",
            "orderBy": "startTime",
            "timeMin": time_min,
            "timeMax": time_max,
            "maxResults": "50",
        }
    )
    url = f"https://www.googleapis.com/calendar/v3/calendars/primary/events?{params}"
    return _http_get(url, token)


def calendar_create(
    token: str,
    *,
    summary: str,
    start: str,
    end: str,
    location: str | None = None,
    description: str | None = None,
) -> dict[str, object]:
    event: dict[str, object] = {
        "summary": summary,
        "start": {"dateTime": start},
        "end": {"dateTime": end},
    }
    if location:
        event["location"] = location
    if description:
        event["description"] = description
    url = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
    result = _http_post(url, token, event)
    return {
        "status": "created",
        "id": result.get("id"),
        "summary": result.get("summary"),
        "htmlLink": result.get("htmlLink"),
    }


def calendar_delete(token: str, *, event_id: str) -> dict[str, object]:
    encoded_id = urllib.parse.quote(event_id, safe="")
    url = f"https://www.googleapis.com/calendar/v3/calendars/primary/events/{encoded_id}"
    _http_delete(url, token)
    return {"status": "deleted", "eventId": event_id}


def _header_value(headers: object, name: str) -> str | None:
    if not isinstance(headers, list):
        return None
    for header in headers:
        if isinstance(header, dict) and header.get("name") == name:
            value = header.get("value")
            return str(value) if value is not None else None
    return None


def _gmail_message_summary(token: str, message_id: str, *, fmt: str = "metadata") -> dict[str, object]:
    query_parts: list[tuple[str, str]] = [("format", fmt)]
    if fmt == "metadata":
        query_parts.extend(
            [
                ("metadataHeaders", "Subject"),
                ("metadataHeaders", "From"),
                ("metadataHeaders", "To"),
            ]
        )
    query = urllib.parse.urlencode(query_parts, doseq=True)
    encoded_id = urllib.parse.quote(message_id, safe="")
    url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{encoded_id}?{query}"
    data = _http_get(url, token)
    payload = data.get("payload")
    headers = payload.get("headers") if isinstance(payload, dict) else None
    result: dict[str, object] = {
        "id": data.get("id", message_id),
        "threadId": data.get("threadId"),
        "snippet": data.get("snippet"),
        "subject": _header_value(headers, "Subject"),
        "from": _header_value(headers, "From"),
        "to": _header_value(headers, "To"),
        "internalDate": data.get("internalDate"),
    }
    if fmt == "full" and isinstance(payload, dict):
        body_data = payload.get("body")
        if isinstance(body_data, dict) and body_data.get("data"):
            try:
                raw = base64.urlsafe_b64decode(str(body_data["data"]))
                result["body"] = raw.decode(errors="replace")
            except Exception:
                result["body"] = ""
    return result


def gmail_get(token: str, message_id: str) -> dict[str, object]:
    return _gmail_message_summary(token, message_id, fmt="full")


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


def _gmail_raw_message(
    *,
    to: str,
    subject: str,
    body: str,
    html: bool = False,
    thread_id: str | None = None,
    in_reply_to: str | None = None,
    references: str | None = None,
) -> dict[str, object]:
    message = MIMEText(body, "html" if html else "plain")
    message["To"] = to
    message["Subject"] = subject
    if in_reply_to:
        message["In-Reply-To"] = in_reply_to
    if references:
        message["References"] = references
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    payload: dict[str, object] = {"raw": raw}
    if thread_id:
        payload["threadId"] = thread_id
    return payload


def gmail_send(
    token: str,
    *,
    to: str,
    subject: str,
    body: str,
    thread_id: str | None = None,
) -> dict[str, object]:
    payload = _gmail_raw_message(to=to, subject=subject, body=body, thread_id=thread_id)
    url = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
    result = _http_post(url, token, payload)
    return {
        "status": "sent",
        "id": result.get("id"),
        "threadId": result.get("threadId"),
    }


def gmail_reply(token: str, *, message_id: str, body: str) -> dict[str, object]:
    original = _gmail_message_summary(token, message_id, fmt="metadata")
    headers_url = (
        f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{urllib.parse.quote(message_id, safe='')}"
        "?format=metadata&metadataHeaders=From&metadataHeaders=Subject&metadataHeaders=Message-ID"
    )
    detail = _http_get(headers_url, token)
    payload = detail.get("payload")
    headers = payload.get("headers") if isinstance(payload, dict) else None
    from_addr = _header_value(headers, "From") or ""
    subject = _header_value(headers, "Subject") or ""
    message_id_header = _header_value(headers, "Message-ID")
    if subject and not subject.startswith("Re:"):
        subject = f"Re: {subject}"
    thread_id = str(original.get("threadId") or detail.get("threadId") or "")
    payload_body = _gmail_raw_message(
        to=from_addr,
        subject=subject,
        body=body,
        thread_id=thread_id or None,
        in_reply_to=message_id_header,
        references=message_id_header,
    )
    url = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
    result = _http_post(url, token, payload_body)
    return {
        "status": "sent",
        "id": result.get("id"),
        "threadId": result.get("threadId"),
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
    parser = argparse.ArgumentParser(description="Google Workspace API helper")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("calendar-today", help="List primary calendar events for today (user timezone)")
    p_range = sub.add_parser("calendar-range", help="List events between RFC3339 timeMin and timeMax")
    p_range.add_argument("--time-min", required=True)
    p_range.add_argument("--time-max", required=True)

    sub.add_parser("gmail-inbox", help="List recent INBOX messages with subject, from, snippet")
    p_get = sub.add_parser("gmail-get", help="Fetch a single message by id")
    p_get.add_argument("message_id")

    sub.add_parser("drive-recent", help="List recently modified Drive files")

    p_send = sub.add_parser("gmail-send", help="Send a new email")
    p_send.add_argument("--to", required=True)
    p_send.add_argument("--subject", required=True)
    p_send.add_argument("--body", required=True)
    p_send.add_argument("--thread-id", default=None)

    p_reply = sub.add_parser("gmail-reply", help="Reply to an existing message")
    p_reply.add_argument("--message-id", required=True)
    p_reply.add_argument("--body", required=True)

    p_create = sub.add_parser("calendar-create", help="Create a calendar event")
    p_create.add_argument("--summary", required=True)
    p_create.add_argument("--start", required=True, help="RFC3339 start datetime")
    p_create.add_argument("--end", required=True, help="RFC3339 end datetime")
    p_create.add_argument("--location", default=None)
    p_create.add_argument("--description", default=None)

    p_delete = sub.add_parser("calendar-delete", help="Delete a calendar event by id")
    p_delete.add_argument("--event-id", required=True)

    args = parser.parse_args()
    token = _require_token()

    if args.command == "calendar-today":
        result = calendar_today(token)
    elif args.command == "calendar-range":
        result = calendar_range(token, time_min=args.time_min, time_max=args.time_max)
    elif args.command == "gmail-inbox":
        result = gmail_inbox(token)
    elif args.command == "gmail-get":
        result = gmail_get(token, args.message_id)
    elif args.command == "drive-recent":
        result = drive_recent(token)
    elif args.command == "gmail-send":
        result = gmail_send(
            token,
            to=args.to,
            subject=args.subject,
            body=args.body,
            thread_id=args.thread_id,
        )
    elif args.command == "gmail-reply":
        result = gmail_reply(token, message_id=args.message_id, body=args.body)
    elif args.command == "calendar-create":
        result = calendar_create(
            token,
            summary=args.summary,
            start=args.start,
            end=args.end,
            location=args.location,
            description=args.description,
        )
    else:
        result = calendar_delete(token, event_id=args.event_id)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
