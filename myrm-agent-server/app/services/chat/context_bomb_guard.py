"""Context bomb guard: parks an oversized user text in the chat's workspace and leaves a stub in its place.

An oversized text (>16,000 characters, or a token pressure >8,000) is saved as a file in the workspace the chat's
agent runs in, and the prompt carries a stub: the start and the end of the text, the file's workspace-relative path
and an instruction to read the file. The text of a person is parked in ``.myrm/pastes`` (kept as long as the
workspace is, and copied along when a chat is forked); a document attached from a messaging channel in
``.myrm/spillover`` (swept after 24 hours).

[INPUT]
- app.services.agent.params.models::MultimodalQuery (POS: agent query payload type)
- app.core.utils.skill_invocation::decorate_behind_skill_tag (POS: keeps a leading ``[use skill]`` tag first)
- app.services.chat.effective_workspace::find_chat_workspace_root (POS: workspace a chat's files live in)
- myrm_agent_harness.agent.context_guard (POS: spillover engine, its two directories and CJK token pressure)

[OUTPUT]
- ContextBombDefenseService: size check, parking of one text or of a query's text, and the sweep of transient files.
- replace_query_text: A query's text swapped for a replacement, its other blocks kept.
- carry_parked_files_to_fork: The parked files a forked conversation names, copied into the fork's workspace.
- SpilloverPayloadResult: Frozen result of parking one text.

[POS]
Chat/Agent ingress safety layer protecting model context window, prompt cache, and billing. One engine writes the
file and renders the stub for every entry (a live turn, a turn with attachments, the stored message), so a stub is
byte-identical wherever it appears and always names a file that is still there.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from myrm_agent_harness.agent.context_guard import (
    KEPT_SPILLOVER_DIR,
    ContextGuardConfig,
    EphemeralTransientSweeper,
    SpilloverEngine,
    estimate_token_pressure,
)

from app.core.utils.skill_invocation import decorate_behind_skill_tag
from app.services.agent.params.models import MultimodalQuery

logger = logging.getLogger(__name__)

_THRESHOLDS = ContextGuardConfig()
# The one place a stub names its file; every stub comes from the engine, so the attribute order is fixed.
_STUB_PATH = re.compile(r'<file_spillover path="([^"]+)"')
_KEPT_ENGINE = SpilloverEngine(ContextGuardConfig(spillover_dir_name=KEPT_SPILLOVER_DIR))
_TRANSIENT_ENGINE = SpilloverEngine()


@dataclass(slots=True, frozen=True)
class SpilloverPayloadResult:
    """Standardized result for chat ingestion pipelines."""

    is_spilled: bool
    processed_content: str
    original_char_count: int
    spillover_path: str | None = None
    # The file's path relative to the workspace: what the stub and the stored message name.
    relative_path: str | None = None
    content_sha256: str | None = None
    estimated_tokens: int = 0
    preview: str = ""

    @classmethod
    def intact(cls, content: str) -> SpilloverPayloadResult:
        """The outcome for a text that stays as it is."""
        return cls(is_spilled=False, processed_content=content, original_char_count=len(content))


def extract_text_from_query(query: MultimodalQuery | object) -> str:
    """Recursively extract all text content from raw query or multimodal blocks."""
    if isinstance(query, str):
        return query
    if isinstance(query, list):
        parts: list[str] = []
        for item in query:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                if item.get("type") == "text" and "text" in item:
                    parts.append(str(item["text"]))
                elif "content" in item and isinstance(item["content"], str):
                    parts.append(str(item["content"]))
                elif "text" in item and isinstance(item["text"], str):
                    parts.append(str(item["text"]))
        return "\n".join(parts)
    return ""


def replace_query_text(query: MultimodalQuery, replacement: str) -> MultimodalQuery:
    """The query with all its text standing as ``replacement``; images and other blocks stay as they are."""
    if isinstance(query, str):
        return replacement

    if isinstance(query, list):
        replaced: list[dict[str, object]] = []
        replaced_text = False
        for item in query:
            if isinstance(item, dict) and item.get("type") == "text":
                if not replaced_text:
                    replaced.append({"type": "text", "text": replacement})
                    replaced_text = True
            else:
                replaced.append(dict(item))
        if not replaced_text:
            replaced.insert(0, {"type": "text", "text": replacement})
        return replaced

    return str(replacement)


class ContextBombDefenseService:
    """Inbound safety gateway preventing context window exhaustion and prompt cache invalidation."""

    @staticmethod
    def is_oversized(content: str) -> bool:
        """Whether ``content`` is too long to go into a prompt as it is."""
        return len(content) > _THRESHOLDS.max_message_chars or estimate_token_pressure(content) > _THRESHOLDS.max_token_pressure

    @staticmethod
    def process_incoming_content(
        content: str,
        *,
        workspace_root: Path | str | None,
        kept: bool = False,
    ) -> SpilloverPayloadResult:
        """Park ``content`` as a file in ``workspace_root`` when it is oversized.

        ``kept`` parks the text of a person (the file is named by a stored message and lives as long as the
        workspace does); without it the file is swept after 24 hours. Without a workspace nothing is written and
        the text stays as it is: there is no directory the agent's file tools could read it back from.

        Raises:
            OSError: The file could not be written.
        """
        if workspace_root is None:
            return SpilloverPayloadResult.intact(content)
        engine = _KEPT_ENGINE if kept else _TRANSIENT_ENGINE
        result = engine.process_content(content, base_dir=workspace_root)
        payload = result.payload
        if not result.spilled or payload is None:
            return SpilloverPayloadResult.intact(content)
        # A leading ``[use skill]`` tag only counts at the very start of the text: keep it in front of the stub.
        stub = decorate_behind_skill_tag(content, lambda _user_text: result.sanitized_content)
        return SpilloverPayloadResult(
            is_spilled=True,
            processed_content=stub,
            original_char_count=payload.char_count,
            spillover_path=payload.file_path,
            relative_path=payload.relative_path,
            content_sha256=payload.sha256_digest,
            estimated_tokens=payload.estimated_tokens,
            preview=payload.summary_preview,
        )

    @staticmethod
    def guard_and_spill_query(
        query: MultimodalQuery,
        workspace_dir: str | Path | None = None,
    ) -> tuple[MultimodalQuery, SpilloverPayloadResult]:
        """The query of a turn, its text parked when oversized (the person's text: kept with the workspace).

        When the file cannot be written the query is returned as it is: the gateway's size backstop applies.
        """
        raw_text = extract_text_from_query(query)
        try:
            parked = ContextBombDefenseService.process_incoming_content(raw_text, workspace_root=workspace_dir, kept=True)
        except OSError:
            logger.warning("A long query could not be saved as a file in its workspace", exc_info=True)
            return query, SpilloverPayloadResult.intact(raw_text)
        if not parked.is_spilled:
            return query, parked
        return replace_query_text(query, parked.processed_content), parked

    @staticmethod
    def sweep_stale_spillover_files(workspace_dir: str | Path | None, ttl_seconds: int | None = None) -> int:
        """Remove the transient files of ``workspace_dir`` older than the TTL (24 hours by default)."""
        if workspace_dir is None:
            return 0
        config = ContextGuardConfig() if ttl_seconds is None else ContextGuardConfig(spillover_ttl_seconds=ttl_seconds)
        return EphemeralTransientSweeper(config).sweep_directory(workspace_dir)


def _is_kept_path(relative_path: str) -> bool:
    """Whether ``relative_path`` names a file directly under the kept directory (no ``..``, not absolute)."""
    parts = PurePosixPath(relative_path).parts
    kept_parts = PurePosixPath(KEPT_SPILLOVER_DIR).parts
    return len(parts) == len(kept_parts) + 1 and parts[:-1] == kept_parts and ".." not in parts


def _carry_parked_files(source: Path, target: Path, relative_paths: Iterable[str]) -> int:
    """Copy the kept files ``relative_paths`` name from workspace ``source`` into workspace ``target``.

    The copy goes through the engine that parked the text: the same text lands under the same name, next to the
    ignore file that keeps it out of version control. A file that is gone, or not a kept file, is skipped.
    """
    if source.resolve() == target.resolve():
        return 0
    carried = 0
    for relative_path in dict.fromkeys(relative_paths):
        origin = source / relative_path
        if not _is_kept_path(relative_path) or not origin.is_file():
            continue
        result = _KEPT_ENGINE.process_content(origin.read_text(encoding="utf-8"), base_dir=target)
        if result.payload is not None and result.payload.relative_path == relative_path:
            carried += 1
    return carried


async def carry_parked_files_to_fork(
    *,
    parent_chat_id: str,
    child_chat_id: str,
    child_workspace: str | None,
    messages: Iterable[str],
) -> int:
    """Copy the parked files the ``messages`` of a fork name from the parent's workspace into the fork's.

    The stubs name a path relative to the workspace, so the child finds the files where it expects them.
    A copy that fails leaves the fork as it is: the stubs still carry the start and the end of each text.

    Returns:
        How many files were copied.
    """
    from app.services.agent.params.workspace_resolve import default_chat_workspace_path
    from app.services.chat.effective_workspace import find_chat_workspace_root

    paths = [path for message in messages for path in _STUB_PATH.findall(message)]
    if not paths:
        return 0
    source = await find_chat_workspace_root(parent_chat_id)
    if source is None:
        return 0
    target = Path(child_workspace) if child_workspace else default_chat_workspace_path(child_chat_id)
    try:
        return await asyncio.to_thread(_carry_parked_files, source, target, paths)
    except OSError:
        logger.warning(
            "Parked files of chat %s could not be copied into its fork %s", parent_chat_id, child_chat_id, exc_info=True
        )
        return 0
