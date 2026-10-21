"""Google Drive folder → wiki raw sync (Google Workspace OAuth).

[INPUT]
- app.services.agent.oauth_refresher (POS: Google OAuth token refresh)
- app.services.wiki.source_sync.content_convert (POS: docx/pdf/text conversion)
- app.services.wiki.source_sync.publish_helpers (POS: publish_raw wrapper)

[OUTPUT]
- sync_gdrive_folder_to_wiki: pull Drive files into wiki raw/gdrive/

[POS]
Deterministic Google Drive ingest path for wiki source sync; zero LLM.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import httpx
from myrm_agent_harness.toolkits.wiki import WikiStructure

from app.database.connection import get_session
from app.services.agent.oauth_refresher import (
    GOOGLE_WORKSPACE_ISSUER,
    refresh_oauth_token,
)
from app.services.integrations.oauth_store import is_oauth_issuer_connected
from app.services.wiki.source_sync.content_convert import bytes_to_wiki_markdown
from app.services.wiki.source_sync.publish_helpers import (
    build_frontmatter,
    publish_source_markdown,
    sanitize_path_segment,
)
from app.services.wiki.source_sync.schemas import WikiSourceSyncResult

logger = logging.getLogger(__name__)

_DRIVE_API = "https://www.googleapis.com/drive/v3/files"

_MIME_GDOC = "application/vnd.google-apps.document"
_MIME_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_MIME_PDF = "application/pdf"
_MIME_MD = "text/markdown"
_MIME_TXT = "text/plain"

_SUPPORTED_MIMES = frozenset({_MIME_GDOC, _MIME_DOCX, _MIME_PDF, _MIME_MD, _MIME_TXT})


async def sync_gdrive_folder_to_wiki(
    structure: WikiStructure,
    *,
    folder_id: str,
    max_items: int,
    auto_compile: bool,
    compiler_enqueue: object | None,
) -> WikiSourceSyncResult:
    result = WikiSourceSyncResult(source="gdrive")
    target_folder = folder_id.strip() or "root"

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
    files = await _list_files(token, folder_id=target_folder, max_results=max_items)
    month = datetime.now(UTC).strftime("%Y-%m")

    for item in files:
        file_id = str(item.get("id", ""))
        if not file_id:
            continue
        name = str(item.get("name", "untitled"))
        mime_type = str(item.get("mimeType", ""))
        modified = str(item.get("modifiedTime", ""))[:10]
        try:
            safe_name = sanitize_path_segment(name.rsplit(".", 1)[0] if "." in name else name)
            relative_path = f"gdrive/{month}/{safe_name}-{sanitize_path_segment(file_id)}.md"
            body = await _download_as_markdown(
                token,
                file_id=file_id,
                name=name,
                mime_type=mime_type,
                structure=structure,
                raw_relative=relative_path,
            )
            if not body:
                result.skipped += 1
                continue
            frontmatter = build_frontmatter(
                source="gdrive",
                title=name,
                external_id=file_id,
                extra={"folder_id": target_folder, "modified": modified},
            )
            content = frontmatter + f"# {name}\n\n{body}\n"
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
                result.errors.append(f"security blocked: {file_id}")
            else:
                result.skipped += 1
        except Exception as exc:
            logger.warning("Google Drive sync failed for %s: %s", file_id, exc)
            result.failed += 1
            result.errors.append(str(exc))

    return result


async def _list_files(token: str, *, folder_id: str, max_results: int) -> list[dict[str, Any]]:
    parent = folder_id if folder_id != "root" else "root"
    query = f"'{parent}' in parents and trashed=false"
    params = {
        "q": query,
        "pageSize": str(max_results),
        "orderBy": "modifiedTime desc",
        "fields": "files(id,name,mimeType,modifiedTime)",
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            _DRIVE_API,
            headers={"Authorization": f"Bearer {token}"},
            params=params,
        )
        resp.raise_for_status()
        data = resp.json()
    raw = data.get("files")
    if not isinstance(raw, list):
        return []
    files: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        mime = str(item.get("mimeType", ""))
        if mime in _SUPPORTED_MIMES:
            files.append(item)
    return files[:max_results]


async def _download_as_markdown(
    token: str,
    *,
    file_id: str,
    name: str,
    mime_type: str,
    structure: WikiStructure,
    raw_relative: str,
) -> str | None:
    if mime_type == _MIME_GDOC:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(
                f"{_DRIVE_API}/{file_id}/export",
                headers={"Authorization": f"Bearer {token}"},
                params={"mimeType": "text/plain"},
            )
            resp.raise_for_status()
            content = resp.content
        return await bytes_to_wiki_markdown(
            content,
            filename=f"{name}.txt",
            mime_type=_MIME_TXT,
            structure=structure,
            raw_relative=raw_relative,
        )

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.get(
            f"{_DRIVE_API}/{file_id}",
            headers={"Authorization": f"Bearer {token}"},
            params={"alt": "media"},
        )
        resp.raise_for_status()
        content = resp.content
    return await bytes_to_wiki_markdown(
        content,
        filename=name,
        mime_type=mime_type,
        structure=structure,
        raw_relative=raw_relative,
    )
