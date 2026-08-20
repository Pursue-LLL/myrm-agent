"""Feishu/Lark document pull → wiki raw sync.

[INPUT]
- app.services.wiki.source_sync.publish_helpers (POS: publish_raw wrapper)
- app.services.wiki.source_sync.schemas (POS: WikiSourceSyncResult)
- app.channels.providers.feishu.sdk.client::FeishuClient (POS: Feishu OpenAPI client)
- app.services.wiki.source_sync.feishu_render (POS: Pure block→Markdown converter for Feishu docs)
- myrm_agent_harness.toolkits.wiki.pipeline.ingress.asset_store (POS: image asset persistence)

[OUTPUT]
- sync_feishu_docs_to_wiki: pull Feishu docs into wiki raw/feishu/
- feishu_docx_blocks_to_markdown: re-export from feishu_render (docx blocks → GFM Markdown)

[POS]
Deterministic Feishu/Lark ingest path for wiki source sync; zero LLM.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from myrm_agent_harness.toolkits.wiki import WikiStructure

from app.services.wiki.source_sync.feishu_render import (
    FEISHU_IMAGE_PREFIX,
    FEISHU_IMAGE_RE,
    feishu_docx_blocks_to_markdown,
)
from app.services.wiki.source_sync.publish_helpers import (
    build_frontmatter,
    publish_source_markdown,
    sanitize_path_segment,
)
from app.services.wiki.source_sync.schemas import WikiSourceSyncResult

if TYPE_CHECKING:
    from app.channels.providers.feishu.sdk.client import FeishuClient

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

    try:
        target_folder = folder_token.strip()
        files = await client.list_drive_folder_files(target_folder, max_items=max_items)
        month = datetime.now(UTC).strftime("%Y-%m")

        for item in files:
            file_token = item.get("token", "")
            file_type = item.get("type", "")
            name = item.get("name", "untitled")
            if not file_token or file_type not in _SUPPORTED_DOC_TYPES:
                result.skipped += 1
                continue
            try:
                safe_name = sanitize_path_segment(name)
                relative_path = f"feishu/{month}/{safe_name}-{sanitize_path_segment(file_token)}.md"
                body = await _fetch_doc_markdown(
                    client,
                    file_token,
                    structure=structure,
                    raw_relative=relative_path,
                )
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
    await client.close()
    return True


async def _resolve_feishu_client() -> FeishuClient | None:
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
    app_secret = str(feishu_cfg.get("app_secret") or feishu_cfg.get("appSecret") or "").strip()
    if not app_id or not app_secret:
        return None

    use_lark = parse_bool(str(feishu_cfg.get("use_lark") or feishu_cfg.get("useLark") or "false"))
    return FeishuClient(app_id, app_secret, use_lark=use_lark)


async def _fetch_doc_markdown(
    client: FeishuClient,
    document_id: str,
    *,
    structure: WikiStructure,
    raw_relative: str,
) -> str | None:
    payload = await client.get_docx_blocks(document_id)
    markdown = feishu_docx_blocks_to_markdown(payload)
    if not markdown:
        return None
    return await _localize_feishu_images(markdown, client, structure=structure, raw_relative=raw_relative)


async def _localize_feishu_images(
    markdown: str,
    client: FeishuClient,
    *,
    structure: WikiStructure,
    raw_relative: str,
) -> str:
    """Download image blocks referenced in markdown and rewrite to wiki assets.

    Download failures (missing scope / 403 / timeouts) degrade to a plain
    ``![image]`` placeholder so a single image never blocks the document.
    """
    tokens = list(dict.fromkeys(FEISHU_IMAGE_RE.findall(markdown)))
    if not tokens:
        return markdown

    from myrm_agent_harness.toolkits.wiki.pipeline.ingress.asset_store import (
        rewrite_markdown_asset_refs,
        store_asset_bytes,
    )

    ref_to_filename: dict[str, str] = {}
    for token in tokens:
        data = await client.download_media(token)
        if not data:
            continue
        filename = store_asset_bytes(
            structure,
            data=data,
            content_type=_guess_image_mime(data),
        )
        if filename:
            ref_to_filename[f"{FEISHU_IMAGE_PREFIX}{token}"] = filename

    rewritten = rewrite_markdown_asset_refs(
        markdown,
        ref_to_filename,
        raw_relative=raw_relative,
    )
    return FEISHU_IMAGE_RE.sub("![image]", rewritten)


def _guess_image_mime(data: bytes) -> str:
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "image/png"
