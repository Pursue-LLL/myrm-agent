"""Feishu/Lark document pull → wiki raw sync."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from myrm_agent_harness.toolkits.wiki import WikiStructure

from app.services.wiki.source_sync.publish_helpers import (
    build_frontmatter,
    publish_source_markdown,
    sanitize_path_segment,
)
from app.services.wiki.source_sync.schemas import WikiSourceSyncResult

logger = logging.getLogger(__name__)

_SUPPORTED_DOC_TYPES = frozenset({"docx", "doc"})


async def sync_feishu_docs_to_wiki(
    structure: WikiStructure,
    *,
    folder_token: str,
    max_items: int,
    auto_compile: bool,
    compiler_enqueue: object | None,
) -> WikiSourceSyncResult:
    result = WikiSourceSyncResult(source="feishu")
    client = await _resolve_feishu_client()
    if client is None:
        result.errors.append("Feishu is not connected")
        return result

    target_folder = folder_token.strip()
    files = await client.list_drive_folder_files(target_folder, max_items=max_items)
    month = datetime.now(UTC).strftime("%Y-%m")

    try:
        for item in files:
            file_token = item.get("token", "")
            file_type = item.get("type", "")
            name = item.get("name", "untitled")
            if not file_token or file_type not in _SUPPORTED_DOC_TYPES:
                result.skipped += 1
                continue
            try:
                safe_name = sanitize_path_segment(name)
                relative_path = (
                    f"feishu/{month}/{safe_name}-{sanitize_path_segment(file_token)}.md"
                )
                body = await _fetch_doc_markdown(client, file_token)
                if not body:
                    result.skipped += 1
                    continue
                frontmatter = build_frontmatter(
                    source="feishu",
                    title=name,
                    external_id=file_token,
                    extra={"folder_token": target_folder, "doc_type": file_type},
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
                    result.errors.append(f"security blocked: {file_token}")
                else:
                    result.skipped += 1
            except Exception as exc:
                logger.warning("Feishu doc sync failed for %s: %s", file_token, exc)
                result.failed += 1
                result.errors.append(str(exc))
    finally:
        await client.close()

    return result


async def is_feishu_wiki_sync_available() -> bool:
    client = await _resolve_feishu_client()
    if client is None:
        return False
    close = getattr(client, "close", None)
    if callable(close):
        await close()
    return True


async def _resolve_feishu_client() -> object | None:
    from app.channels.core.credentials import parse_bool
    from app.channels.providers.feishu.sdk.client import FeishuClient
    from app.core.channel_bridge.credential_spec import load_from_db

    raw = await load_from_db("channels")
    if not isinstance(raw, dict):
        return None
    feishu_cfg = raw.get("feishu")
    if not isinstance(feishu_cfg, dict):
        return None
    if feishu_cfg.get("enabled") is False:
        return None

    app_id = str(feishu_cfg.get("app_id") or feishu_cfg.get("appId") or "").strip()
    app_secret = str(
        feishu_cfg.get("app_secret") or feishu_cfg.get("appSecret") or ""
    ).strip()
    if not app_id or not app_secret:
        return None

    use_lark = parse_bool(
        str(feishu_cfg.get("use_lark") or feishu_cfg.get("useLark") or "false")
    )
    return FeishuClient(app_id, app_secret, use_lark=use_lark)


async def _fetch_doc_markdown(client: object, document_id: str) -> str | None:
    get_blocks = getattr(client, "get_docx_blocks", None)
    if not callable(get_blocks):
        return None
    payload = await get_blocks(document_id)
    return feishu_docx_blocks_to_markdown(payload)


def feishu_docx_blocks_to_markdown(payload: dict[str, object]) -> str | None:
    data = payload.get("data")
    if not isinstance(data, dict):
        return None
    items = data.get("items")
    if not isinstance(items, list):
        return None

    lines: list[str] = []
    for block in items:
        if not isinstance(block, dict):
            continue
        block_type = block.get("block_type")
        if block_type in {3, 4, 5}:
            heading_level = {3: 1, 4: 2, 5: 3}.get(int(block_type), 1)
            text = _block_text(block)
            if text:
                lines.append(f"{'#' * heading_level} {text}")
            continue
        if block_type == 2:
            text = _block_text(block)
            if text:
                lines.append(text)
            continue
        if block_type == 12:
            text = _block_text(block)
            if text:
                lines.append(f"- {text}")

    body = "\n\n".join(lines).strip()
    return body or None


def _block_text(block: dict[str, object]) -> str:
    for key in ("text", "heading1", "heading2", "heading3", "bullet"):
        section = block.get(key)
        if isinstance(section, dict):
            return _text_elements_to_str(section.get("elements"))
    return ""


def _text_elements_to_str(elements: object) -> str:
    if not isinstance(elements, list):
        return ""
    parts: list[str] = []
    for element in elements:
        if not isinstance(element, dict):
            continue
        text_run = element.get("text_run")
        if isinstance(text_run, dict):
            content = text_run.get("content")
            if isinstance(content, str) and content:
                parts.append(content)
    return "".join(parts).strip()
