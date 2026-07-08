#!/usr/bin/env python3
"""IMAP/SMTP email management helper for the imap-smtp-email prebuilt skill.

[INPUT]
- Process env EMAIL_IMAP_HOST, EMAIL_IMAP_USER, EMAIL_IMAP_PASSWORD (injected by skill runtime)
- Process env EMAIL_SMTP_HOST, EMAIL_SMTP_USER, EMAIL_SMTP_PASSWORD (optional, for send/reply)
- Process env EMAIL_IMAP_PORT (default 993), EMAIL_SMTP_PORT (default 587)

[OUTPUT]
- JSON on stdout for all CLI subcommands

[POS]
Vendor skill script staged into workspace by bash_executor; stdlib-only IMAP/SMTP client.
"""

from __future__ import annotations

import argparse
import email as email_lib
import email.header
import email.mime.multipart
import email.mime.text
import email.utils
import imaplib
import json
import os
import smtplib
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import NoReturn


def _fail(message: str, *, code: int = 1) -> NoReturn:
    print(json.dumps({"error": message}))
    sys.exit(code)


def _require_env(key: str, default: str = "") -> str:
    value = os.environ.get(key, default).strip()
    if not value:
        _fail(f"Environment variable {key} is not set")
    return value


def _get_imap_config() -> tuple[str, int, str, str]:
    host = _require_env("EMAIL_IMAP_HOST")
    port = int(os.environ.get("EMAIL_IMAP_PORT", "993").strip() or "993")
    user = _require_env("EMAIL_IMAP_USER")
    password = _require_env("EMAIL_IMAP_PASSWORD")
    return host, port, user, password


def _get_smtp_config() -> tuple[str, int, str, str]:
    host = os.environ.get("EMAIL_SMTP_HOST", "").strip()
    if not host:
        imap_host = _require_env("EMAIL_IMAP_HOST")
        host = imap_host.replace("imap.", "smtp.")
    port = int(os.environ.get("EMAIL_SMTP_PORT", "587").strip() or "587")
    user = os.environ.get("EMAIL_SMTP_USER", "").strip() or _require_env("EMAIL_IMAP_USER")
    password = os.environ.get("EMAIL_SMTP_PASSWORD", "").strip() or _require_env("EMAIL_IMAP_PASSWORD")
    return host, port, user, password


def _send_imap_id(conn: imaplib.IMAP4_SSL) -> None:
    """Send RFC 2971 IMAP ID command. Required by 163/NetEase after LOGIN."""
    try:
        conn.xatom(
            "ID",
            '("name" "myrm-agent" "version" "1" '
            '"vendor" "myrm" "support-email" "noreply@myrm.sh")',
        )
    except Exception:
        pass


_IMAP_TIMEOUT = 30


def _connect_imap() -> imaplib.IMAP4_SSL:
    host, port, user, password = _get_imap_config()
    try:
        conn = imaplib.IMAP4_SSL(host, port, timeout=_IMAP_TIMEOUT)
        conn.login(user, password)
        _send_imap_id(conn)
        return conn
    except imaplib.IMAP4.error as exc:
        _fail(f"IMAP authentication failed: {exc}")
    except (OSError, TimeoutError) as exc:
        _fail(f"IMAP connection failed: {exc}")


def _decode_header(raw: str | None) -> str:
    if not raw:
        return ""
    parts = email.header.decode_header(raw)
    decoded: list[str] = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(part)
    return " ".join(decoded)


def _parse_date(raw: str | None) -> str:
    if not raw:
        return ""
    try:
        parsed = email.utils.parsedate_to_datetime(raw)
        return parsed.isoformat()
    except Exception:
        return raw


def _message_summary(msg: email_lib.message.Message, uid: int) -> dict[str, object]:
    return {
        "uid": uid,
        "from": _decode_header(msg.get("From", "")),
        "to": _decode_header(msg.get("To", "")),
        "subject": _decode_header(msg.get("Subject", "")),
        "date": _parse_date(msg.get("Date")),
        "message_id": msg.get("Message-ID", ""),
    }


def _extract_body(msg: email_lib.message.Message) -> str:
    if not msg.is_multipart():
        payload = msg.get_payload(decode=True)
        if isinstance(payload, bytes):
            charset = msg.get_content_charset() or "utf-8"
            return payload.decode(charset, errors="replace")
        return ""

    text_body = ""
    html_body = ""
    for part in msg.walk():
        ct = part.get_content_type()
        disp = str(part.get("Content-Disposition", ""))
        if "attachment" in disp:
            continue
        payload = part.get_payload(decode=True)
        if not isinstance(payload, bytes):
            continue
        charset = part.get_content_charset() or "utf-8"
        decoded = payload.decode(charset, errors="replace")
        if ct == "text/plain" and not text_body:
            text_body = decoded
        elif ct == "text/html" and not html_body:
            html_body = decoded

    return text_body or html_body


def _date_criteria(since: str | None) -> str:
    """Convert relative date string (e.g. '7d', '30d', '2h') to IMAP SINCE date."""
    if not since:
        return ""
    since = since.strip().lower()
    now = datetime.now()
    try:
        if since.endswith("d"):
            days = int(since[:-1])
            target = now - timedelta(days=days)
        elif since.endswith("h"):
            hours = int(since[:-1])
            target = now - timedelta(hours=hours)
        elif since.endswith("w"):
            weeks = int(since[:-1])
            target = now - timedelta(weeks=weeks)
        else:
            return f'SINCE "{since}"'
    except (ValueError, OverflowError):
        _fail(f"Invalid --since format: '{since}'. Use e.g. '7d', '24h', '2w'")
    return f'SINCE "{target.strftime("%d-%b-%Y")}"'


def _fetch_headers(conn: imaplib.IMAP4_SSL, criteria: str, limit: int) -> None:
    """Search mailbox and print JSON summary of matching message headers."""
    _status, msg_nums = conn.uid("search", None, criteria)
    if not msg_nums or not msg_nums[0]:
        print(json.dumps({"messages": [], "total": 0}))
        return

    uids = msg_nums[0].split()
    recent_uids = uids[-limit:]

    messages: list[dict[str, object]] = []
    for uid_bytes in reversed(recent_uids):
        uid = int(uid_bytes)
        _status, data = conn.uid("fetch", str(uid), "(RFC822.HEADER)")
        if not data or not data[0] or not isinstance(data[0], tuple):
            continue
        raw = data[0][1]
        if isinstance(raw, bytes):
            msg = email_lib.message_from_bytes(raw)
            messages.append(_message_summary(msg, uid))

    print(json.dumps({"messages": messages, "total": len(uids)}, ensure_ascii=False, indent=2))


def cmd_check(args: argparse.Namespace) -> None:
    conn = _connect_imap()
    try:
        folder = args.folder or "INBOX"
        conn.select(folder, readonly=True)

        criteria_parts: list[str] = []
        if args.unread_only:
            criteria_parts.append("UNSEEN")
        if not criteria_parts:
            criteria_parts.append("ALL")

        _fetch_headers(conn, f"({' '.join(criteria_parts)})", args.limit or 20)
    finally:
        conn.logout()


def cmd_search(args: argparse.Namespace) -> None:
    conn = _connect_imap()
    try:
        folder = args.folder or "INBOX"
        conn.select(folder, readonly=True)

        criteria_parts: list[str] = []
        if args.sender:
            criteria_parts.append(f'FROM "{args.sender}"')
        if args.subject:
            criteria_parts.append(f'SUBJECT "{args.subject}"')
        if args.to:
            criteria_parts.append(f'TO "{args.to}"')
        if args.since:
            date_crit = _date_criteria(args.since)
            if date_crit:
                criteria_parts.append(date_crit)
        if args.keyword:
            criteria_parts.append(f'BODY "{args.keyword}"')

        if not criteria_parts:
            _fail("At least one search criterion is required (--from, --subject, --to, --since, --keyword)")

        _fetch_headers(conn, f"({' '.join(criteria_parts)})", args.limit or 20)
    finally:
        conn.logout()


def cmd_read(args: argparse.Namespace) -> None:
    conn = _connect_imap()
    try:
        folder = args.folder or "INBOX"
        conn.select(folder, readonly=True)

        _status, data = conn.uid("fetch", str(args.uid), "(RFC822)")
        if not data or not data[0] or not isinstance(data[0], tuple):
            _fail(f"Message UID {args.uid} not found")

        raw = data[0][1]
        if not isinstance(raw, bytes):
            _fail(f"Message UID {args.uid} has no content")

        msg = email_lib.message_from_bytes(raw)
        summary = _message_summary(msg, args.uid)
        summary["body"] = _extract_body(msg)

        attachments: list[dict[str, str]] = []
        if msg.is_multipart():
            for part in msg.walk():
                disp = str(part.get("Content-Disposition", ""))
                if "attachment" in disp:
                    filename = part.get_filename() or "attachment"
                    filename = _decode_header(filename)
                    attachments.append({
                        "filename": filename,
                        "content_type": part.get_content_type(),
                    })
        summary["attachments"] = attachments

        print(json.dumps(summary, ensure_ascii=False, indent=2))
    finally:
        conn.logout()


def cmd_download(args: argparse.Namespace) -> None:
    conn = _connect_imap()
    try:
        folder = args.folder or "INBOX"
        conn.select(folder, readonly=True)

        _status, data = conn.uid("fetch", str(args.uid), "(RFC822)")
        if not data or not data[0] or not isinstance(data[0], tuple):
            _fail(f"Message UID {args.uid} not found")

        raw = data[0][1]
        if not isinstance(raw, bytes):
            _fail(f"Message UID {args.uid} has no content")

        msg = email_lib.message_from_bytes(raw)
        saved: list[dict[str, object]] = []
        output_dir = Path(args.output_dir or tempfile.gettempdir())
        output_dir.mkdir(parents=True, exist_ok=True)

        target_filename = getattr(args, "filename", None)
        for part in msg.walk():
            disp = str(part.get("Content-Disposition", ""))
            if "attachment" not in disp:
                continue
            filename = part.get_filename() or "attachment"
            filename = _decode_header(filename)
            if target_filename and target_filename.lower() not in filename.lower():
                continue
            file_data = part.get_payload(decode=True)
            if not isinstance(file_data, bytes):
                continue
            safe_name = "".join(c if c.isalnum() or c in "._-" else "_" for c in filename)
            dest = output_dir / safe_name
            dest.write_bytes(file_data)
            saved.append({"filename": filename, "path": str(dest), "size": len(file_data)})

        if not saved:
            print(json.dumps({"status": "no_attachments", "message": "No attachments found in this message"}))
        else:
            print(json.dumps({"status": "downloaded", "files": saved}, ensure_ascii=False, indent=2))
    finally:
        conn.logout()


def cmd_send(args: argparse.Namespace) -> None:
    host, port, user, password = _get_smtp_config()
    from_addr = os.environ.get("EMAIL_FROM_ADDRESS", "").strip() or user

    msg = email.mime.multipart.MIMEMultipart("alternative")
    msg["From"] = from_addr
    msg["To"] = args.to
    msg["Subject"] = args.subject
    msg_id = email.utils.make_msgid()
    msg["Message-ID"] = msg_id
    msg.attach(email.mime.text.MIMEText(args.body, "plain", "utf-8"))

    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=30) as server:
                server.login(user, password)
                server.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=30) as server:
                server.starttls()
                server.login(user, password)
                server.send_message(msg)
        print(json.dumps({"status": "sent", "message_id": msg_id, "to": args.to}))
    except smtplib.SMTPAuthenticationError as exc:
        _fail(f"SMTP authentication failed: {exc}")
    except (smtplib.SMTPException, OSError) as exc:
        _fail(f"SMTP send failed: {exc}")


def cmd_reply(args: argparse.Namespace) -> None:
    conn = _connect_imap()
    try:
        folder = args.folder or "INBOX"
        conn.select(folder, readonly=True)

        _status, data = conn.uid("fetch", str(args.uid), "(RFC822)")
        if not data or not data[0] or not isinstance(data[0], tuple):
            _fail(f"Message UID {args.uid} not found")

        raw = data[0][1]
        if not isinstance(raw, bytes):
            _fail(f"Message UID {args.uid} has no content")

        original = email_lib.message_from_bytes(raw)
    finally:
        conn.logout()

    from_header = original.get("From", "")
    reply_to = original.get("Reply-To", from_header)
    _, reply_addr = email.utils.parseaddr(reply_to)
    subject = _decode_header(original.get("Subject", ""))
    if not subject.startswith("Re:"):
        subject = f"Re: {subject}"
    original_msg_id = original.get("Message-ID", "")
    references = original.get("References", "")
    if original_msg_id:
        references = f"{references} {original_msg_id}".strip()

    host, port, user, password = _get_smtp_config()
    from_addr = os.environ.get("EMAIL_FROM_ADDRESS", "").strip() or user

    msg = email.mime.multipart.MIMEMultipart("alternative")
    msg["From"] = from_addr
    msg["To"] = reply_addr
    msg["Subject"] = subject
    msg_id = email.utils.make_msgid()
    msg["Message-ID"] = msg_id
    if original_msg_id:
        msg["In-Reply-To"] = original_msg_id
    if references:
        msg["References"] = references
    msg.attach(email.mime.text.MIMEText(args.body, "plain", "utf-8"))

    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=30) as server:
                server.login(user, password)
                server.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=30) as server:
                server.starttls()
                server.login(user, password)
                server.send_message(msg)
        print(json.dumps({
            "status": "sent",
            "message_id": msg_id,
            "to": reply_addr,
            "subject": subject,
        }))
    except smtplib.SMTPAuthenticationError as exc:
        _fail(f"SMTP authentication failed: {exc}")
    except (smtplib.SMTPException, OSError) as exc:
        _fail(f"SMTP send failed: {exc}")


def cmd_mark_read(args: argparse.Namespace) -> None:
    conn = _connect_imap()
    try:
        folder = args.folder or "INBOX"
        conn.select(folder, readonly=False)
        uids = [u.strip() for u in args.uids.split(",") if u.strip()]
        if not uids:
            _fail("At least one UID is required")
        for uid in uids:
            conn.uid("store", uid, "+FLAGS", "(\\Seen)")
        print(json.dumps({"status": "marked_read", "uids": uids}))
    finally:
        conn.logout()


def cmd_mark_unread(args: argparse.Namespace) -> None:
    conn = _connect_imap()
    try:
        folder = args.folder or "INBOX"
        conn.select(folder, readonly=False)
        uids = [u.strip() for u in args.uids.split(",") if u.strip()]
        if not uids:
            _fail("At least one UID is required")
        for uid in uids:
            conn.uid("store", uid, "-FLAGS", "(\\Seen)")
        print(json.dumps({"status": "marked_unread", "uids": uids}))
    finally:
        conn.logout()


def cmd_folders(args: argparse.Namespace) -> None:
    conn = _connect_imap()
    try:
        _status, folder_list = conn.list()
        folders: list[str] = []
        if folder_list:
            for item in folder_list:
                if isinstance(item, bytes):
                    decoded = item.decode("utf-8", errors="replace")
                    parts = decoded.rsplit('" ', 1)
                    if len(parts) == 2:
                        folders.append(parts[1].strip('"'))
                    else:
                        folders.append(decoded)
        print(json.dumps({"folders": folders}, ensure_ascii=False, indent=2))
    finally:
        conn.logout()


def main() -> None:
    parser = argparse.ArgumentParser(description="IMAP/SMTP Email Manager")
    sub = parser.add_subparsers(dest="command", required=True)

    p_check = sub.add_parser("check", help="Check inbox for messages")
    p_check.add_argument("--unread-only", action="store_true", help="Only show unread messages")
    p_check.add_argument("--limit", type=int, default=20, help="Max messages to return")
    p_check.add_argument("--folder", default="INBOX", help="Mailbox folder")

    p_search = sub.add_parser("search", help="Search messages with criteria")
    p_search.add_argument("--from", dest="sender", help="Filter by sender address")
    p_search.add_argument("--to", help="Filter by recipient")
    p_search.add_argument("--subject", help="Filter by subject keyword")
    p_search.add_argument("--since", help="Messages since (e.g. 7d, 30d, 2w)")
    p_search.add_argument("--keyword", help="Search in message body")
    p_search.add_argument("--limit", type=int, default=20, help="Max messages to return")
    p_search.add_argument("--folder", default="INBOX", help="Mailbox folder")

    p_read = sub.add_parser("read", help="Read full message content")
    p_read.add_argument("uid", type=int, help="Message UID")
    p_read.add_argument("--folder", default="INBOX", help="Mailbox folder")

    p_download = sub.add_parser("download", help="Download message attachments")
    p_download.add_argument("uid", type=int, help="Message UID")
    p_download.add_argument("--filename", help="Download only attachment matching this name")
    p_download.add_argument("--output-dir", help="Directory to save attachments")
    p_download.add_argument("--folder", default="INBOX", help="Mailbox folder")

    p_send = sub.add_parser("send", help="Send a new email")
    p_send.add_argument("--to", required=True, help="Recipient email address")
    p_send.add_argument("--subject", required=True, help="Email subject")
    p_send.add_argument("--body", required=True, help="Email body text")

    p_reply = sub.add_parser("reply", help="Reply to an existing message")
    p_reply.add_argument("--uid", type=int, required=True, help="UID of message to reply to")
    p_reply.add_argument("--body", required=True, help="Reply body text")
    p_reply.add_argument("--folder", default="INBOX", help="Mailbox folder")

    p_mark_read = sub.add_parser("mark-read", help="Mark messages as read")
    p_mark_read.add_argument("uids", help="Comma-separated UIDs to mark as read")
    p_mark_read.add_argument("--folder", default="INBOX", help="Mailbox folder")

    p_mark_unread = sub.add_parser("mark-unread", help="Mark messages as unread")
    p_mark_unread.add_argument("uids", help="Comma-separated UIDs to mark as unread")
    p_mark_unread.add_argument("--folder", default="INBOX", help="Mailbox folder")

    sub.add_parser("folders", help="List available mailbox folders")

    args = parser.parse_args()

    commands = {
        "check": cmd_check,
        "search": cmd_search,
        "read": cmd_read,
        "download": cmd_download,
        "send": cmd_send,
        "reply": cmd_reply,
        "mark-read": cmd_mark_read,
        "mark-unread": cmd_mark_unread,
        "folders": cmd_folders,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
