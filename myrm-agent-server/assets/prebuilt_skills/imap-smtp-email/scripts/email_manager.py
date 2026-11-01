#!/usr/bin/env python3
"""IMAP/SMTP email management helper for the imap-smtp-email prebuilt skill.

[INPUT]
- Process env EMAIL_IMAP_HOST, EMAIL_IMAP_USER, EMAIL_IMAP_PASSWORD (injected by skill runtime)
- Process env EMAIL_SMTP_HOST, EMAIL_SMTP_USER, EMAIL_SMTP_PASSWORD (optional, for send/reply)
- Process env EMAIL_IMAP_PORT (default 993), EMAIL_SMTP_PORT (default 587)
- Process env SSL_CERT_FILE (optional): PEM bundle that replaces the default trust store, for servers signed by a private CA
- mail_client.transport: verified IMAP/SMTP connections, quoted command arguments, and the JSON error exit
- mail_client.message: MIME header, date, summary, attachment, reply recipients and body decoding
- mail_client.attachments: saving a download under a safe name as a new file, never over one that exists

[OUTPUT]
- JSON on stdout for all subcommands; failures are {"error": ...} with exit code 1, except a non-numeric port and unencodable output
- read lists the parts the sender attached, however the disposition is written, a message that is one attachment included;
  download saves those that carry bytes (an attached message/rfc822 is listed, not saved); reply goes to every address of Reply-To,
  else of From, and is refused when neither holds an address
- download never overwrites: a name taken on disk or by an earlier attachment gets ``-1`` to ``-999``, then it is an error;
  a name is made safe and short enough for the file system; a write that fails leaves no file behind, and the error lists
  the files saved before it

[POS]
Vendor skill script staged into workspace by bash_executor; stdlib-only IMAP/SMTP client. This file holds the
subcommands and the argument parser; the connection, message and attachment logic lives in the sibling mail_client
package, which Python resolves through the script directory on sys.path. The package ships without __init__.py because
the prebuilt seed sync skips paths with an underscore-prefixed part, so it is a namespace package.
"""

from __future__ import annotations

import argparse
import email as email_lib
import email.message
import email.mime.multipart
import email.mime.text
import email.utils
import imaplib
import json
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from mail_client.attachments import save_new
from mail_client.message import (
    ascii_msg_ids,
    attachment_filename,
    attachment_parts,
    decode_header,
    extract_body,
    message_summary,
    reply_recipients,
)
from mail_client.transport import (
    connect_imap,
    deliver,
    fail,
    get_smtp_config,
    imap_quote,
    json_errors,
    parse_uids,
    select_folder,
)


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
            return f"SINCE {imap_quote(since)}"
    except (ValueError, OverflowError):
        fail(f"Invalid --since format: '{since}'. Use e.g. '7d', '24h', '2w'")
    return f'SINCE "{target.strftime("%d-%b-%Y")}"'


def _fetch_headers(conn: imaplib.IMAP4_SSL, criteria: str, limit: int) -> None:
    """Search mailbox and print JSON summary of matching message headers."""
    _status, msg_nums = conn.uid("search", criteria)
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
            messages.append(message_summary(msg, uid))

    print(json.dumps({"messages": messages, "total": len(uids)}, ensure_ascii=False, indent=2))


def _fetch_message(conn: imaplib.IMAP4_SSL, uid: int) -> email.message.Message:
    """The full message *uid* of the selected folder; the command fails when it is gone or empty."""
    _status, data = conn.uid("fetch", str(uid), "(RFC822)")
    if not data or not data[0] or not isinstance(data[0], tuple):
        fail(f"Message UID {uid} not found")

    raw = data[0][1]
    if not isinstance(raw, bytes):
        fail(f"Message UID {uid} has no content")

    return email_lib.message_from_bytes(raw)


def cmd_check(args: argparse.Namespace) -> None:
    conn = connect_imap()
    try:
        folder = args.folder or "INBOX"
        select_folder(conn, folder, readonly=True)

        criteria_parts: list[str] = []
        if args.unread_only:
            criteria_parts.append("UNSEEN")
        if not criteria_parts:
            criteria_parts.append("ALL")

        _fetch_headers(conn, f"({' '.join(criteria_parts)})", args.limit or 20)
    finally:
        conn.logout()


def cmd_search(args: argparse.Namespace) -> None:
    conn = connect_imap()
    try:
        folder = args.folder or "INBOX"
        select_folder(conn, folder, readonly=True)

        criteria_parts: list[str] = []
        if args.sender:
            criteria_parts.append(f"FROM {imap_quote(args.sender)}")
        if args.subject:
            criteria_parts.append(f"SUBJECT {imap_quote(args.subject)}")
        if args.to:
            criteria_parts.append(f"TO {imap_quote(args.to)}")
        if args.since:
            date_crit = _date_criteria(args.since)
            if date_crit:
                criteria_parts.append(date_crit)
        if args.keyword:
            criteria_parts.append(f"BODY {imap_quote(args.keyword)}")

        if not criteria_parts:
            fail("At least one search criterion is required (--from, --subject, --to, --since, --keyword)")

        _fetch_headers(conn, f"({' '.join(criteria_parts)})", args.limit or 20)
    finally:
        conn.logout()


def cmd_read(args: argparse.Namespace) -> None:
    conn = connect_imap()
    try:
        folder = args.folder or "INBOX"
        select_folder(conn, folder, readonly=True)

        msg = _fetch_message(conn, args.uid)
        summary = message_summary(msg, args.uid)
        summary["body"] = extract_body(msg)

        summary["attachments"] = [
            {"filename": attachment_filename(part), "content_type": part.get_content_type()} for part in attachment_parts(msg)
        ]

        print(json.dumps(summary, ensure_ascii=False, indent=2))
    finally:
        conn.logout()


def _save_attachments(msg: email.message.Message, output_dir: Path, name_filter: str | None) -> list[dict[str, object]]:
    """Save the attachments of *msg* whose name holds *name_filter* as new files in *output_dir*.

    A failure after some files are saved names them in the error, because they stay on disk.
    """
    saved: list[dict[str, object]] = []
    try:
        for part in attachment_parts(msg):
            filename = attachment_filename(part)
            if name_filter and name_filter.lower() not in filename.lower():
                continue
            file_data = part.get_payload(decode=True)
            if not isinstance(file_data, bytes):
                continue
            dest = save_new(output_dir, filename, file_data)
            saved.append({"filename": filename, "path": str(dest), "size": len(file_data)})
    except OSError as exc:
        if not saved:
            raise
        raise OSError(f"{exc}; already saved: {', '.join(str(entry['path']) for entry in saved)}") from exc
    return saved


def cmd_download(args: argparse.Namespace) -> None:
    conn = connect_imap()
    try:
        folder = args.folder or "INBOX"
        select_folder(conn, folder, readonly=True)

        msg = _fetch_message(conn, args.uid)
        output_dir = Path(args.output_dir or tempfile.gettempdir())
        output_dir.mkdir(parents=True, exist_ok=True)

        saved = _save_attachments(msg, output_dir, getattr(args, "filename", None))
        if not saved:
            print(json.dumps({"status": "no_attachments", "message": "No attachments found in this message"}))
        else:
            print(json.dumps({"status": "downloaded", "files": saved}, ensure_ascii=False, indent=2))
    finally:
        conn.logout()


def cmd_send(args: argparse.Namespace) -> None:
    host, port, user, password = get_smtp_config()
    from_addr = os.environ.get("EMAIL_FROM_ADDRESS", "").strip() or user

    msg = email.mime.multipart.MIMEMultipart("alternative")
    msg["From"] = from_addr
    msg["To"] = args.to
    msg["Subject"] = args.subject
    msg_id = email.utils.make_msgid()
    msg["Message-ID"] = msg_id
    msg.attach(email.mime.text.MIMEText(args.body, "plain", "utf-8"))

    deliver(msg, host, port, user, password)
    print(json.dumps({"status": "sent", "message_id": msg_id, "to": args.to}))


def cmd_reply(args: argparse.Namespace) -> None:
    conn = connect_imap()
    try:
        folder = args.folder or "INBOX"
        select_folder(conn, folder, readonly=True)

        original = _fetch_message(conn, args.uid)
    finally:
        conn.logout()

    recipients = reply_recipients(original)
    if not recipients:
        fail("The message has no Reply-To or From address to reply to")
    subject = decode_header(original.get("Subject", ""))
    if not subject.startswith("Re:"):
        subject = f"Re: {subject}"
    original_msg_id = ascii_msg_ids(original.get("Message-ID", ""))
    references = ascii_msg_ids(original.get("References", ""))
    if original_msg_id:
        references = f"{references} {original_msg_id}".strip()

    host, port, user, password = get_smtp_config()
    from_addr = os.environ.get("EMAIL_FROM_ADDRESS", "").strip() or user

    msg = email.mime.multipart.MIMEMultipart("alternative")
    msg["From"] = from_addr
    msg["To"] = recipients
    msg["Subject"] = subject
    msg_id = email.utils.make_msgid()
    msg["Message-ID"] = msg_id
    if original_msg_id:
        msg["In-Reply-To"] = original_msg_id
    if references:
        msg["References"] = references
    msg.attach(email.mime.text.MIMEText(args.body, "plain", "utf-8"))

    deliver(msg, host, port, user, password)
    print(json.dumps({"status": "sent", "message_id": msg_id, "to": recipients, "subject": subject}))


def cmd_mark_read(args: argparse.Namespace) -> None:
    conn = connect_imap()
    try:
        folder = args.folder or "INBOX"
        select_folder(conn, folder, readonly=False)
        uids = parse_uids(args.uids)
        for uid in uids:
            conn.uid("store", uid, "+FLAGS", "(\\Seen)")
        print(json.dumps({"status": "marked_read", "uids": uids}))
    finally:
        conn.logout()


def cmd_mark_unread(args: argparse.Namespace) -> None:
    conn = connect_imap()
    try:
        folder = args.folder or "INBOX"
        select_folder(conn, folder, readonly=False)
        uids = parse_uids(args.uids)
        for uid in uids:
            conn.uid("store", uid, "-FLAGS", "(\\Seen)")
        print(json.dumps({"status": "marked_unread", "uids": uids}))
    finally:
        conn.logout()


def cmd_folders(args: argparse.Namespace) -> None:
    conn = connect_imap()
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
    with json_errors(args.command):
        commands[args.command](args)


if __name__ == "__main__":
    main()
