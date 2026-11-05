"""Wiki 批量导入的写盘、冲突校验与结果统计。

[POS]
folder/zip/obsidian/urls/video 五条导入路径共用；不感知具体来源。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from fastapi import HTTPException

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.wiki.core.structure import WikiStructure
    from myrm_agent_harness.toolkits.wiki.pipeline.raw_gate import RawPublishResult

logger = logging.getLogger(__name__)


async def _schedule_post_import_dedup_scan(agent_id: str | None) -> None:
    try:
        from app.services.wiki.dedup_runner import schedule_wiki_dedup_scan

        await schedule_wiki_dedup_scan(agent_id=agent_id, incremental=True)
    except Exception as exc:
        logger.warning("Post-import wiki dedup scan failed: %s", exc)


async def _publish_import_raw(
    structure: "WikiStructure",
    relative_path: str,
    content: str,
    *,
    on_conflict: Literal["skip", "supersede"],
    supersede_reason: str,
) -> RawPublishResult:
    from myrm_agent_harness.toolkits.wiki.pipeline.raw_gate import (
        RawConflictPolicy,
        RawGateError,
        RawPublishRequest,
        publish_raw,
    )

    policy = RawConflictPolicy.SUPERSEDE if on_conflict == "supersede" else RawConflictPolicy.SKIP
    try:
        return await publish_raw(
            structure,
            RawPublishRequest(
                relative_path=relative_path,
                content=content,
                conflict_policy=policy,
                supersede_reason=supersede_reason,
            ),
            caller="settings",
        )
    except RawGateError as exc:
        if exc.code == "invalid_request":
            raise HTTPException(
                status_code=422,
                detail={"code": exc.code, "message": exc.message},
            ) from exc
        raise


def _validate_import_conflict_options(
    on_conflict: Literal["skip", "supersede"],
    supersede_reason: str,
) -> None:
    if on_conflict == "supersede" and not supersede_reason.strip():
        raise HTTPException(
            status_code=422,
            detail={
                "code": "invalid_request",
                "message": "supersede_reason is required when on_conflict is supersede.",
            },
        )


def _track_import_publish_result(
    result: RawPublishResult,
    *,
    enqueued_paths: list[Path],
    conflict_paths: list[str],
    security_blocked_paths: list[str],
    security_redacted_paths: list[str],
) -> tuple[int, int]:
    """Returns (skipped_conflict_count, superseded_count) for one publish result."""
    if result.security_blocked:
        security_blocked_paths.append(result.relative_path)
        return 0, 0
    if result.written:
        enqueued_paths.append(result.absolute_path)
        if result.security_redacted:
            security_redacted_paths.append(result.relative_path)
    if result.conflict_skipped:
        conflict_paths.append(result.relative_path)
        return 1, 0
    if result.superseded:
        return 0, 1
    return 0, 0


def _build_import_message(
    *,
    enqueued: int,
    skipped_conflict: int,
    superseded: int,
    security_blocked: int,
    security_redacted: int,
    auto_compile: bool,
    source_label: str = "",
) -> str:
    parts = [f"Imported {enqueued} file(s){source_label}"]
    if skipped_conflict:
        parts.append(f"{skipped_conflict} conflict(s) skipped")
    if superseded:
        parts.append(f"{superseded} superseded")
    if security_blocked:
        parts.append(f"{security_blocked} blocked (sensitive content)")
    if security_redacted:
        parts.append(f"{security_redacted} redacted")
    parts.append("compilation started" if auto_compile else "queued without auto-compile")
    return ", ".join(parts)
