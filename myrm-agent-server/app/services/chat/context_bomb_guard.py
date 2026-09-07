"""Context Bomb Guard and Transparent File Spillover Engine.

Detects oversized incoming user payloads (>16,000 characters or >8,000 token pressure), safely offloads them
to POSIX-isolated sandbox workspace files (.myrm/spillover/payload_<sha256>.md),
and transparently injects structured XML file references into the agent prompt context.

[INPUT]
- app.services.agent.params.models::MultimodalQuery (POS: agent query payload type)
- myrm_agent_harness.agent.context_guard (POS: harness spillover engine and CJK token pressure)
- pathlib.Path, hashlib, time, uuid

[OUTPUT]
- ContextBombDefenseService: Inbound query guard, spillover manager, and stale file sweeper.
- SpilloverMetadata: Metadata describing spilled payloads.
- SpilloverPayloadResult: Frozen result tuple for high-level pipeline compatibility.

[POS]
Chat/Agent ingress safety layer protecting model context window, prompt cache, and billing.
"""

from __future__ import annotations

import contextlib
import hashlib
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final
from uuid import uuid4

from app.services.agent.params.models import MultimodalQuery
from myrm_agent_harness.agent.context_guard import (
    ContextGuardConfig,
    EphemeralTransientSweeper,
    SpilloverEngine,
    estimate_token_pressure,
)

logger = logging.getLogger(__name__)

MESSAGE_MAX_CHARS: Final[int] = 16_000
MAX_TOKEN_PRESSURE: Final[int] = 8_000
PREVIEW_MAX_CHARS: Final[int] = 300
SPILLED_DIR_NAME: Final[str] = ".myrm/spillover"
SPILLED_FILE_TTL_SECONDS: Final[float] = 86_400.0  # 24 hours
DIR_PERMISSIONS: Final[int] = 0o700
FILE_PERMISSIONS: Final[int] = 0o600


@dataclass(slots=True)
class SpilloverMetadata:
    """Metadata regarding a spilled text payload."""

    sha256: str
    file_path: str
    total_chars: int
    preview: str
    estimated_tokens: int = 0
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, object]:
        return {
            "sha256": self.sha256,
            "filePath": self.file_path,
            "totalChars": self.total_chars,
            "preview": self.preview,
            "estimatedTokens": self.estimated_tokens,
            "createdAt": self.created_at,
        }


@dataclass(slots=True, frozen=True)
class SpilloverPayloadResult:
    """Standardized result for chat ingestion pipelines."""

    is_spilled: bool
    processed_content: str
    original_char_count: int
    spillover_path: str | None = None
    content_sha256: str | None = None
    estimated_tokens: int = 0


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


def build_spillover_prompt_block(
    file_path: str,
    total_chars: int,
    sha256: str,
    preview: str,
    estimated_tokens: int = 0,
) -> str:
    """Construct structured, prompt-cache-friendly XML reference block."""
    token_hint = f", ~{estimated_tokens:,} tokens" if estimated_tokens > 0 else ""
    return (
        f"<file_spillover path=\"{file_path}\" total_chars=\"{total_chars}\" sha256=\"{sha256[:16]}\">\n"
        f"<preview>\n{preview}\n...\n</preview>\n"
        f"<instruction>\n"
        f"Notice: User provided a large document payload ({total_chars:,} characters{token_hint}) that exceeds direct context threshold.\n"
        f"It has been safely preserved at '{file_path}'.\n"
        f"When detailed analysis, code inspection, or specific section retrieval is required, use the 'read_file' tool to inspect this file.\n"
        f"</instruction>\n"
        f"</file_spillover>"
    )


class ContextBombDefenseService:
    """Inbound safety gateway preventing context window exhaustion and prompt cache invalidation."""

    def __init__(
        self,
        max_chars: int = MESSAGE_MAX_CHARS,
        max_tokens: int = MAX_TOKEN_PRESSURE,
        preview_chars: int = PREVIEW_MAX_CHARS,
        ttl_seconds: float = SPILLED_FILE_TTL_SECONDS,
    ) -> None:
        self.max_chars = max_chars
        self.max_tokens = max_tokens
        self.preview_chars = preview_chars
        self.ttl_seconds = ttl_seconds
        self._harness_engine = SpilloverEngine(
            ContextGuardConfig(
                max_message_chars=max_chars,
                max_token_pressure=max_tokens,
                preview_chars=preview_chars,
                spillover_ttl_seconds=int(ttl_seconds),
            )
        )
        self._harness_sweeper = EphemeralTransientSweeper(
            ContextGuardConfig(spillover_ttl_seconds=int(ttl_seconds))
        )

    @classmethod
    def get_spillover_dir(cls, workspace_root: Path | str | None = None) -> Path:
        """Resolve and initialize the transient spillover storage directory."""
        if workspace_root is None:
            base_dir = Path.home() / ".myrm" / "spillover"
        else:
            base_dir = Path(workspace_root) / ".myrm" / "spillover"

        base_dir.mkdir(parents=True, exist_ok=True)
        with contextlib.suppress(OSError):
            os.chmod(base_dir, DIR_PERMISSIONS)
        return base_dir

    @classmethod
    def process_incoming_content(
        cls,
        content: str,
        *,
        chat_id: str | None = None,
        workspace_root: Path | str | None = None,
        max_chars: int = MESSAGE_MAX_CHARS,
    ) -> SpilloverPayloadResult:
        """Inspect plain text message length and transparently spill to workspace file if exceeding cap."""
        char_count = len(content)
        token_pressure = estimate_token_pressure(content)

        if char_count <= max_chars and token_pressure <= MAX_TOKEN_PRESSURE:
            return SpilloverPayloadResult(
                is_spilled=False,
                processed_content=content,
                original_char_count=char_count,
                estimated_tokens=token_pressure,
            )

        sha256_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        short_hash = sha256_hash[:16]
        preview = content[:PREVIEW_MAX_CHARS].strip()

        target_dir = cls.get_spillover_dir(workspace_root)
        target_file = target_dir / f"payload_{short_hash}.md"

        # Security check: verify no path traversal
        try:
            target_file.resolve().relative_to(target_dir.resolve())
        except ValueError as err:
            logger.error("Security violation: spillover path escaped target dir: %s", target_file)
            raise PermissionError("Path traversal violation in spillover directory") from err

        # Idempotent atomic file write with unique tmp file
        if not target_file.exists():
            tmp_file = target_dir / f".tmp_{short_hash}_{uuid4().hex[:6]}"
            try:
                tmp_file.write_text(content, encoding="utf-8")
                with contextlib.suppress(OSError):
                    os.chmod(tmp_file, FILE_PERMISSIONS)
                tmp_file.replace(target_file)
            except Exception as e:
                logger.error("Failed to write transient spillover file: %s", e, exc_info=True)
                truncated = content[:max_chars]
                return SpilloverPayloadResult(
                    is_spilled=False,
                    processed_content=truncated + f"\n\n[System Warning: Text truncated to {max_chars} chars due to file spillover write failure]",
                    original_char_count=char_count,
                    estimated_tokens=token_pressure,
                )
            finally:
                if tmp_file.exists():
                    with contextlib.suppress(OSError):
                        tmp_file.unlink(missing_ok=True)

        rel_file_path = str(target_file.resolve())
        prompt_block = build_spillover_prompt_block(
            file_path=rel_file_path,
            total_chars=char_count,
            sha256=sha256_hash,
            preview=preview,
            estimated_tokens=token_pressure,
        )

        logger.info(
            "ContextBombDefenseService mitigated large payload: chars=%d (~%d tokens) sha256=%s path=%s for chat_id=%s",
            char_count,
            token_pressure,
            short_hash,
            rel_file_path,
            chat_id or "unknown",
        )

        return SpilloverPayloadResult(
            is_spilled=True,
            processed_content=prompt_block,
            original_char_count=char_count,
            spillover_path=rel_file_path,
            content_sha256=sha256_hash,
            estimated_tokens=token_pressure,
        )

    def guard_and_spill_query(
        self,
        query: MultimodalQuery,
        workspace_dir: str | Path | None = None,
        session_id: str | None = None,
    ) -> tuple[MultimodalQuery, bool, SpilloverMetadata | None]:
        """Inspect inbound query for context bomb conditions.

        If total character length or token pressure exceeds limit, transparently saves payload
        to sandbox workspace file and returns a transformed query with structured XML reference.
        """
        raw_text = extract_text_from_query(query)
        char_count = len(raw_text)
        token_pressure = estimate_token_pressure(raw_text)

        if char_count <= self.max_chars and token_pressure <= self.max_tokens:
            return query, False, None

        sha256_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
        short_hash = sha256_hash[:16]
        preview = raw_text[: self.preview_chars].strip()

        # Resolve destination storage root
        if workspace_dir:
            base_dir = Path(workspace_dir).resolve()
            spill_dir = base_dir / SPILLED_DIR_NAME
            rel_file_path = f"{SPILLED_DIR_NAME}/payload_{short_hash}.md"
        else:
            fallback_sid = session_id or "default"
            base_dir = Path("/tmp/myrm_spillover").resolve() / fallback_sid
            spill_dir = base_dir
            rel_file_path = str(spill_dir / f"payload_{short_hash}.md")

        spill_dir.mkdir(parents=True, exist_ok=True)
        with contextlib.suppress(OSError):
            os.chmod(spill_dir, DIR_PERMISSIONS)

        target_file = spill_dir / f"payload_{short_hash}.md"
        # Anti-directory-traversal security verification
        try:
            target_file.resolve().relative_to(spill_dir.resolve())
        except ValueError as err:
            logger.error("Security violation: spillover path escaped target dir: %s", target_file)
            raise PermissionError("Path traversal violation in spillover directory") from err

        # Idempotent atomic write with unique temp file
        if not target_file.exists():
            tmp_file = spill_dir / f".tmp_{short_hash}_{uuid4().hex[:6]}"
            try:
                tmp_file.write_text(raw_text, encoding="utf-8")
                with contextlib.suppress(OSError):
                    os.chmod(tmp_file, FILE_PERMISSIONS)
                tmp_file.replace(target_file)
                logger.info(
                    "ContextBombDefenseService spilled large payload: chars=%d tokens=%d sha256=%s path=%s",
                    char_count,
                    token_pressure,
                    short_hash,
                    rel_file_path,
                )
            finally:
                if tmp_file.exists():
                    with contextlib.suppress(OSError):
                        tmp_file.unlink(missing_ok=True)

        metadata = SpilloverMetadata(
            sha256=sha256_hash,
            file_path=rel_file_path,
            total_chars=char_count,
            preview=preview,
            estimated_tokens=token_pressure,
        )

        prompt_block = build_spillover_prompt_block(
            file_path=rel_file_path,
            total_chars=char_count,
            sha256=sha256_hash,
            preview=preview,
            estimated_tokens=token_pressure,
        )

        transformed_query = self._transform_query_with_spillover(query, prompt_block)
        return transformed_query, True, metadata

    def _transform_query_with_spillover(
        self,
        query: MultimodalQuery,
        prompt_block: str,
    ) -> MultimodalQuery:
        """Replace oversized text payload with structured file reference block."""
        if isinstance(query, str):
            return prompt_block

        if isinstance(query, list):
            transformed_list: list[dict[str, object]] = []
            replaced_text = False
            for item in query:
                if isinstance(item, dict) and item.get("type") == "text":
                    if not replaced_text:
                        transformed_list.append({"type": "text", "text": prompt_block})
                        replaced_text = True
                else:
                    transformed_list.append(dict(item))
            if not replaced_text:
                transformed_list.insert(0, {"type": "text", "text": prompt_block})
            return transformed_list

        return str(prompt_block)

    def sweep_stale_spillover_files(
        self,
        workspace_dir: str | Path | None = None,
        ttl_seconds: float | None = None,
    ) -> int:
        """Purge spilled files older than TTL (default 24h) to avoid disk exhaustion."""
        effective_ttl = ttl_seconds if ttl_seconds is not None else self.ttl_seconds
        purged = 0
        if workspace_dir:
            purged += self._harness_sweeper.sweep_directory(workspace_dir)

        fallback_dir = Path("/tmp/myrm_spillover").resolve()
        if fallback_dir.exists():
            now = time.time()
            cutoff = now - effective_ttl
            for entry in fallback_dir.rglob("payload_*.md"):
                try:
                    if entry.stat().st_mtime < cutoff:
                        entry.unlink(missing_ok=True)
                        purged += 1
                except OSError as err:
                    logger.debug("Failed cleaning stale spillover file %s: %s", entry, err)

        if purged > 0:
            logger.info("ContextBombDefenseService swept %d stale spillover files", purged)
        return purged

    @classmethod
    def cleanup_transient_spillover_cache(
        cls,
        workspace_root: Path | str | None = None,
        ttl_seconds: float = SPILLED_FILE_TTL_SECONDS,
    ) -> int:
        """Alias for sweep_stale_spillover_files matching classmethod contract."""
        inst = get_context_bomb_defense_service()
        return inst.sweep_stale_spillover_files(workspace_dir=workspace_root, ttl_seconds=ttl_seconds)


_GLOBAL_CONTEXT_BOMB_GUARD = ContextBombDefenseService()


def get_context_bomb_defense_service() -> ContextBombDefenseService:
    """Return singleton instance of ContextBombDefenseService."""
    return _GLOBAL_CONTEXT_BOMB_GUARD
