"""Multimodal reads for file_read_tool: image, PDF, document and video blocks, and their text-mode fallbacks.

[INPUT]
- file_read.text_paths::process_text_paths (POS: text path read: modes, page cap, structure outline, per-file redaction)
- utils.*_reader (POS: image/pdf/video/document readers)
- utils.vault_read::read_vault_paths_to_parts (POS: vault URI batch reader)
- agent.security.redact::redact_sensitive_text, redact_extracted_text (POS: tool output redaction; redaction of the text a reader extracted, by file type)
- core.security.tool_registry::strip_read_range (POS: the file path of a path argument, without its ``:START-END`` range)
- backends.skills.types::SkillMetadata (POS: MCP skill metadata)

[OUTPUT]
- build_multimodal_result: multimodal content blocks for vision/document paths
- append_media_text_parts: text-mode fallbacks for image/pdf/document/video

[POS]
Multimodal read execution for file_read_tool. The text of every block it returns is redacted as its file's type is,
a notebook as source code; plain text paths are read in text_paths.py, the way a call without media reads them.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, cast

from langchain_core.messages.content import ContentBlock, create_text_block
from langchain_core.runnables import RunnableConfig

from myrm_agent_harness.agent.security.redact import redact_extracted_text, redact_sensitive_text
from myrm_agent_harness.core.security.tool_registry import strip_read_range

from ...utils.document_reader import read_document_as_text, read_document_multimodal
from ...utils.image_reader import read_image_as_content_blocks
from ...utils.pdf_reader import read_pdf_as_content_blocks
from ...utils.vault_read import read_vault_paths_to_parts
from ...utils.video_reader import read_video_as_content_blocks
from .text_paths import process_text_paths

if TYPE_CHECKING:
    from myrm_agent_harness.backends.skills.types import SkillMetadata
    from myrm_agent_harness.toolkits.code_execution.executors.base import CodeExecutor

logger = logging.getLogger(__name__)


async def _read_image_via_ocr(img_path: str, executor: CodeExecutor) -> str | None:
    """Last-resort OCR text for an image when the model cannot see and no chain exists.

    ``OcrTierEngine`` is the documented final tier of the vision pipeline; without this
    call a text-only model with no configured vision route gets nothing but a metadata
    line for every image it reads. Returns ``None`` when the OCR extra is absent or the
    image holds no readable text, so the caller keeps its metadata response instead of
    reporting an unexamined image as empty.
    """
    from myrm_agent_harness.toolkits.llms.vision.ocr_tier import NO_READABLE_TEXT, OcrTierEngine

    try:
        vision_result = await OcrTierEngine().describe_local_image(img_path, executor)
    except Exception as e:
        logger.warning("OCR tier unavailable for %s: %s", img_path, e)
        return None
    text = vision_result.text.strip()
    if not text or text == NO_READABLE_TEXT:
        return None
    return f"[Image OCR for {img_path}]:\n{text}"


def _as_blocks(result: str | list[ContentBlock]) -> list[ContentBlock]:
    """A reader's answer as content blocks: a plain string is one text block."""
    return result if isinstance(result, list) else [create_text_block(result)]


def _redact_text_blocks(blocks: list[ContentBlock], path: str) -> list[ContentBlock]:
    """``blocks`` with the text of each redacted as the text extracted from ``path``; an image block stays as it is."""
    base = strip_read_range(path)
    redacted: list[ContentBlock] = []
    for block in blocks:
        fields = cast("dict[str, object]", block)
        text = fields.get("text")
        if fields.get("type") == "text" and isinstance(text, str):
            redacted.append(cast("ContentBlock", {**fields, "text": redact_extracted_text(base, text)}))
        else:
            redacted.append(block)
    return redacted


async def build_multimodal_result(
    image_paths: list[str],
    pdf_paths: list[str],
    document_paths: list[str],
    text_paths: list[str],
    vault_paths: list[str],
    executor: CodeExecutor,
    skills: list[SkillMetadata] | None,
    reason: str | None,
    url_errors: list[str],
    supports_vision: bool,
    supports_video: bool = False,
    vision_fallback_model_cfg: object | None = None,
    vision_fallback_model_cfgs: object | None = None,
    video_fallback_model_cfgs: object | None = None,
    video_paths: list[str] | None = None,
    parse_mode: str | None = None,
    mode: str = "all",
    *,
    config: RunnableConfig,
) -> list[ContentBlock]:
    """Build multimodal result: images/PDFs as content blocks, documents/text as text blocks.

    Every text block is redacted: the text of a media or document block as its file's type is, a URL refusal and
    vault text in full, and text paths by ``process_text_paths``. Images pass through as they are.
    """
    blocks: list[ContentBlock] = []

    if url_errors:
        blocks.append(create_text_block(redact_sensitive_text("\n".join(url_errors))))

    for img_path in image_paths:
        shown: list[ContentBlock] = []
        if supports_vision:
            shown.extend(_as_blocks(await read_image_as_content_blocks(img_path, executor, supports_vision=True)))
        elif vision_fallback_model_cfg is not None or vision_fallback_model_cfgs is not None:
            from myrm_agent_harness.toolkits.llms.vision.fallback_engine import (
                create_vision_fallback_engine,
            )

            try:
                engine = create_vision_fallback_engine(
                    vision_fallback_model_cfg,
                    vision_fallback_model_cfgs,
                )
                if engine is None:
                    raise ValueError("Vision fallback engine is not configured")
                fallback_text = await engine.describe_local_image(img_path, executor)
                shown.append(create_text_block(f"[Image Analysis for {img_path}]:\n{fallback_text}"))
            except Exception as e:
                logger.warning("Vision fallback failed for %s: %s", img_path, e)
                shown.append(create_text_block(f"[Image file: {img_path}] (Vision analysis unavailable)"))
        else:
            ocr_text = await _read_image_via_ocr(img_path, executor)
            if ocr_text is not None:
                shown.append(create_text_block(ocr_text))
            else:
                shown.extend(_as_blocks(await read_image_as_content_blocks(img_path, executor, supports_vision=False)))
        blocks.extend(_redact_text_blocks(shown, img_path))

    for pdf_path in pdf_paths:
        result = await read_pdf_as_content_blocks(
            pdf_path,
            executor,
            supports_vision=supports_vision,
            vision_fallback_model_cfg=vision_fallback_model_cfg,
            vision_fallback_model_cfgs=vision_fallback_model_cfgs,
            parse_mode=parse_mode,
        )
        blocks.extend(_redact_text_blocks(_as_blocks(result), pdf_path))

    for doc_path in document_paths:
        doc_blocks = await read_document_multimodal(
            doc_path,
            executor,
            supports_vision=supports_vision,
            parse_mode=parse_mode,
        )
        blocks.extend(_redact_text_blocks(doc_blocks, doc_path))

    for vid_path in video_paths or []:
        result = await read_video_as_content_blocks(
            vid_path,
            executor,
            supports_vision=supports_vision,
            supports_video=supports_video,
            vision_fallback_model_cfg=vision_fallback_model_cfg,
            vision_fallback_model_cfgs=vision_fallback_model_cfgs,
            video_fallback_model_cfgs=video_fallback_model_cfgs,
        )
        blocks.extend(_redact_text_blocks(_as_blocks(result), vid_path))

    if vault_paths:
        vault_parts = await read_vault_paths_to_parts(vault_paths, executor, mode, config=config)
        if vault_parts:
            blocks.append(create_text_block(redact_sensitive_text("\n\n".join(vault_parts))))

    if text_paths:
        text = "\n\n".join(
            await process_text_paths(text_paths, executor, skills, reason, mode, config=config, parse_mode=parse_mode)
        )
        if text:
            blocks.append(create_text_block(text))

    return blocks if blocks else [create_text_block("No results.")]


async def append_media_text_parts(
    text_parts: list[str],
    *,
    image_paths: list[str],
    pdf_paths: list[str],
    document_paths: list[str],
    video_paths: list[str],
    executor: CodeExecutor | None,
    supports_vision: bool,
    supports_video: bool = False,
    vision_fallback_model_cfg: object | None,
    vision_fallback_model_cfgs: object | None = None,
    video_fallback_model_cfgs: object | None = None,
    parse_mode: str | None,
) -> None:
    """Append text-mode results for media paths when multimodal is unavailable."""
    for img_path in image_paths:
        if executor is not None:
            if supports_vision:
                img_result = await read_image_as_content_blocks(img_path, executor, supports_vision=True)
                if isinstance(img_result, str):
                    text_parts.append(img_result)
            elif vision_fallback_model_cfg is not None or vision_fallback_model_cfgs is not None:
                from myrm_agent_harness.toolkits.llms.vision.fallback_engine import (
                    create_vision_fallback_engine,
                )

                try:
                    engine = create_vision_fallback_engine(
                        vision_fallback_model_cfg,
                        vision_fallback_model_cfgs,
                    )
                    if engine is None:
                        raise ValueError("Vision fallback engine is not configured")
                    fallback_text = await engine.describe_local_image(img_path, executor)
                    text_parts.append(f"[Image Analysis for {img_path}]:\n{fallback_text}")
                except Exception as e:
                    logger.warning("Vision fallback failed for %s: %s", img_path, e)
                    text_parts.append(f"[Image file: {img_path}] (Vision analysis unavailable)")
            else:
                img_result = await read_image_as_content_blocks(img_path, executor, supports_vision=False)
                if isinstance(img_result, str):
                    text_parts.append(img_result)
        else:
            text_parts.append(f"[Image file: {img_path}] (No workspace filesystem available)")

    for pdf_path in pdf_paths:
        if executor is not None:
            pdf_result = await read_pdf_as_content_blocks(
                pdf_path,
                executor,
                supports_vision=False,
                vision_fallback_model_cfg=vision_fallback_model_cfg,
                vision_fallback_model_cfgs=vision_fallback_model_cfgs,
                parse_mode=parse_mode,
            )
            # With an auxiliary vision chain the reader returns blocks; flatten their text so
            # this text-mode path keeps the document instead of silently dropping it.
            if isinstance(pdf_result, list):
                for block in pdf_result:
                    if isinstance(block, dict) and block.get("type") == "text":
                        block_text = cast("dict[str, object]", block).get("text")
                        if isinstance(block_text, str):
                            text_parts.append(block_text)
            else:
                text_parts.append(pdf_result)
        else:
            text_parts.append(f"[PDF file: {pdf_path}] (No workspace filesystem available)")

    for doc_path in document_paths:
        if executor is not None:
            doc_result = await read_document_as_text(doc_path, executor, parse_mode=parse_mode)
            text_parts.append(doc_result)
        else:
            text_parts.append(f"[Document: {doc_path}] (No workspace filesystem available)")

    for vid_path in video_paths:
        if executor is not None:
            vid_result = await read_video_as_content_blocks(
                vid_path,
                executor,
                supports_vision=supports_vision,
                supports_video=supports_video,
                vision_fallback_model_cfg=vision_fallback_model_cfg,
                vision_fallback_model_cfgs=vision_fallback_model_cfgs,
                video_fallback_model_cfgs=video_fallback_model_cfgs,
            )
            if isinstance(vid_result, str):
                text_parts.append(vid_result)
        else:
            text_parts.append(f"[Video file: {vid_path}] (No workspace filesystem available)")
