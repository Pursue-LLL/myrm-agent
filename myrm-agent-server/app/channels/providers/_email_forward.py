"""Forwarded email detection and structured parsing for EmailChannel.

Detects forwarded emails via three strategies:
1. Subject prefix (Fwd:, FW:, 转发:, 轉發:)
2. Body separator (Gmail/Outlook/QQ standard separators)
3. MIME message/rfc822 embedded attachment

[INPUT]
- Raw email body text (str)

[OUTPUT]
- Parsed forwarded metadata dict, or None if not forwarded

[POS]
Forwarded email parsing utilities. Separates user annotation from original
email content and extracts structured header information.
"""

from __future__ import annotations

import re

_FWD_SEPARATOR_RE = re.compile(
    r"^-{3,}\s*"
    r"(?:Forwarded message|Original Message|转发邮件|轉發郵件)"
    r"\s*-{3,}\s*$",
    re.MULTILINE | re.IGNORECASE,
)
_FWD_HEADER_RE = re.compile(
    r"^(?:From|Date|Subject|To|Cc|发件人|日期|主题|收件人)\s*[:：]\s*(.+)$",
    re.MULTILINE | re.IGNORECASE,
)

FWD_SUBJECT_PREFIXES = ("fwd:", "fw:", "转发:", "轉發:")


def parse_forwarded_body(body: str) -> dict[str, str] | None:
    """Detect forwarded-message separator and split user annotation from original.

    Returns a dict with ``annotation``, ``forwarded_body``, and any extracted
    forwarded headers (``forwarded_from``, ``forwarded_subject``, etc.)
    if a forwarded separator is found; ``None`` otherwise.
    """
    match = _FWD_SEPARATOR_RE.search(body)
    if not match:
        return None

    annotation = body[: match.start()].strip()
    remainder = body[match.end() :]

    headers: dict[str, str] = {}
    body_start = 0
    for hdr_match in _FWD_HEADER_RE.finditer(remainder):
        key = hdr_match.group(0).split(":")[0].split("：")[0].strip().lower()
        val = hdr_match.group(1).strip()
        if key in ("from", "发件人"):
            headers["forwarded_from"] = val
        elif key in ("subject", "主题"):
            headers["forwarded_subject"] = val
        elif key in ("date", "日期"):
            headers["forwarded_date"] = val
        elif key in ("to", "收件人"):
            headers["forwarded_to"] = val
        body_start = hdr_match.end()

    forwarded_body = remainder[body_start:].strip() if body_start else remainder.strip()

    result: dict[str, str] = {"annotation": annotation, "forwarded_body": forwarded_body}
    result.update(headers)
    return result
