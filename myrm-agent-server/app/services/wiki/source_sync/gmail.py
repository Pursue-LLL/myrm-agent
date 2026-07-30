"""Gmail label → wiki raw sync (Google Workspace OAuth)."""

from __future__ import annotations

import base64
import logging
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from app.database.connection import get_session
from app.services.agent.oauth_refresher import GOOGLE_WORKSPACE_ISSUER, refresh_oauth_token
from app.services.integrations.oauth_store import is_oauth_issuer_connected
from app.services.wiki.source_sync.html_body import html_body_to_markdown
from app.services.wiki.source_sync.publish_helpers import build_frontmatter, publish_source_markdown, sanitize_path_segment
from app.services.wiki.source_sync.schemas import WikiSourceSyncResult
from myrm_agent_harness.toolkits.wiki import WikiStructure

logger = logging.getLogger(__name__)

_GMAIL_API = "https://gmail.googleapis.com/gmail/v1/users/me"


async def sync_gmail_label_to_wiki(
    structure: WikiStructure,
    *,
    label: str,
    max_items: int,
    auto_compile: bool,
    compiler_enqueue: object | None,
) -> WikiSourceSyncResult:
    result = WikiSourceSyncResult(source="gmail")
    label_name = label.strip() or "ReadLater"

    async with get_session() as db:
        connected = await is_oauth_issuer_connected(db, GOOGLE_WORKSPACE_ISSUER)
    if not connected:
        result.errors.append("Google Workspace is not connected")
        return result

    credential = await refresh_oauth_token(GOOGLE_WORKSPACE_ISSUER)
    if credential is None or not credential.token:
        result.errors.append("Google OAuth token unavailable")
        return result

    token = credential.token
    label_id = await _resolve_label_id(token, label_name)
    if label_id is None:
        result.errors.append(f"Gmail label not found: {label_name}")
        return result

    message_ids = await _list_message_ids(token, label_id=label_id, max_results=max_items)
    month = datetime.now(UTC).strftime("%Y-%m")

    for message_id in message_ids:
        try:
            doc = await _fetch_message_markdown(token, message_id)
            if not doc:
                result.skipped += 1
                continue
            title, body, received = doc
            safe_id = sanitize_path_segment(message_id)
            relative_path = f"gmail/{month}/{safe_id}.md"
            frontmatter = build_frontmatter(
                source="gmail",
                title=title,
                external_id=message_id,
                extra={"label": label_name, "received": received},
            )
            content = frontmatter + f"# {title}\n\n{body}\n"
            publish = await publish_source_markdown(
                structure,
                relative_path=relative_path,
                content=content,
                auto_compile=auto_compile,
                compiler_enqueue=compiler_enqueue,
            )
            if publish.written:
                result.published += 1
            elif publish.conflict_skipped or publish.skipped:
                result.skipped += 1
            elif publish.security_blocked:
                result.failed += 1
                result.errors.append(f"security blocked: {message_id}")
            else:
                result.skipped += 1
        except Exception as exc:
            logger.warning("Gmail sync failed for %s: %s", message_id, exc)
            result.failed += 1
            result.errors.append(str(exc))

    return result


async def _resolve_label_id(token: str, label_name: str) -> str | None:
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(
            f"{_GMAIL_API}/labels",
            headers={"Authorization": f"Bearer {token}"},
        )
        resp.raise_for_status()
        data = resp.json()
    labels = data.get("labels")
    if not isinstance(labels, list):
        return None
    target = label_name.strip().lower()
    for item in labels:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", ""))
        if name.lower() == target:
            label_id = item.get("id")
            return str(label_id) if label_id else None
    return None


async def _list_message_ids(token: str, *, label_id: str, max_results: int) -> list[str]:
    params = {"labelIds": label_id, "maxResults": str(max_results)}
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(
            f"{_GMAIL_API}/messages",
            headers={"Authorization": f"Bearer {token}"},
            params=params,
        )
        resp.raise_for_status()
        data = resp.json()
    raw = data.get("messages")
    if not isinstance(raw, list):
        return []
    ids: list[str] = []
    for item in raw:
        if isinstance(item, dict):
            mid = item.get("id")
            if isinstance(mid, str) and mid:
                ids.append(mid)
    return ids


async def _fetch_message_markdown(token: str, message_id: str) -> tuple[str, str, str] | None:
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{_GMAIL_API}/messages/{message_id}",
            headers={"Authorization": f"Bearer {token}"},
            params={"format": "full"},
        )
        resp.raise_for_status()
        data = resp.json()

    payload = data.get("payload")
    if not isinstance(payload, dict):
        return None
    headers = payload.get("headers")
    subject = _header(headers, "Subject") or "(no subject)"
    date_header = _header(headers, "Date") or ""
    received = _format_date(date_header)
    plain, html = _extract_bodies(payload)
    body = plain.strip() if plain.strip() else html_body_to_markdown(html)
    if not body.strip():
        snippet = data.get("snippet")
        body = str(snippet) if snippet else ""
    if not body.strip():
        return None
    return subject, body, received


def _header(headers: object, name: str) -> str | None:
    if not isinstance(headers, list):
        return None
    for item in headers:
        if isinstance(item, dict) and item.get("name") == name:
            value = item.get("value")
            return str(value) if value is not None else None
    return None


def _format_date(date_header: str) -> str:
    if not date_header:
        return datetime.now(UTC).strftime("%Y-%m-%d")
    try:
        parsed = parsedate_to_datetime(date_header)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC).strftime("%Y-%m-%d")
    except (TypeError, ValueError, OverflowError):
        return datetime.now(UTC).strftime("%Y-%m-%d")


def _extract_bodies(payload: dict[str, Any]) -> tuple[str, str]:
    plain_parts: list[str] = []
    html_parts: list[str] = []
    _walk_parts(payload, plain_parts, html_parts)
    return "\n\n".join(plain_parts), "\n\n".join(html_parts)


def _walk_parts(part: dict[str, Any], plain_parts: list[str], html_parts: list[str]) -> None:
    mime = str(part.get("mimeType", ""))
    body = part.get("body")
    data_b64 = body.get("data") if isinstance(body, dict) else None
    if isinstance(data_b64, str) and data_b64:
        try:
            decoded = base64.urlsafe_b64decode(data_b64).decode(errors="replace")
            if mime == "text/plain":
                plain_parts.append(decoded)
            elif mime == "text/html":
                html_parts.append(decoded)
        except Exception:
            pass
    nested = part.get("parts")
    if isinstance(nested, list):
        for child in nested:
            if isinstance(child, dict):
                _walk_parts(child, plain_parts, html_parts)


