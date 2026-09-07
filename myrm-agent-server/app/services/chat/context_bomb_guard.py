"""Context Bomb Guard and Transparent File Spillover Engine.

Detects oversized incoming user payloads (>16,000 characters), safely offloads them
to POSIX-isolated sandbox workspace files (.myrm/spillover/payload_<sha256>.md),
and transparently injects structured file references into the agent prompt context.

[INPUT]
- app.schemas.custom_types: MultimodalQuery (str | list[dict[str, object]])
- pathlib.Path, hashlib, time

[OUTPUT]
- ContextBombDefenseService: Inbound query guard, spillover manager, and stale file sweeper.
- SpilloverResult: Metadata describing spilled payloads.

[POS]
Chat/Agent ingress safety layer protecting model context window, prompt cache, and billing.
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

from app.schemas.custom_types import MultimodalQuery

logger = logging.getLogger(__name__)

MESSAGE_MAX_CHARS: int = 16_000
PREVIEW_MAX_CHARS: int = 300
SPILLED_DIR_NAME: str = ".myrm/spillover"
SPILLED_FILE_TTL_SECONDS: float = 86_400.0  # 24 hours
DIR_PERMISSIONS: int = 0o700
FILE_PERMISSIONS: int = 0o600


@dataclass(slots=True)
class SpilloverMetadata:
    """Metadata regarding a spilled text payload."""

    sha256: str
    file_path: str
    total_chars: int
    preview: str
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, object]:
        return {
            "sha256": self.sha256,
            "filePath": self.file_path,
            "totalChars": self.total_chars,
            "preview": self.preview,
            "createdAt": self.created_at,
        }


def extract_text_from_query(query: MultimodalQuery | object) -> str:
    """Recursively extract all text content from raw query or multimodal blocks."""
    if isinstance(query, str):
        return query
    if isinstance(query, list):
        parts: list[str] = []
        for item in query:
            if isinstance(item, dict):
                text_val = item.get("text")
                if isinstance(text_val, str):
                    parts.append(text_val)
        return "\n".join(parts)
    return ""


def build_spillover_prompt_block(
    file_path: str,
    total_chars: int,
    sha256: str,
    preview: str,
) -> str:
    """Construct structured, prompt-cache-friendly XML reference block."""
    return (
        f"<file_spillover path=\"{file_path}\" total_chars=\"{total_chars}\" sha256=\"{sha256}\">\n"
        f"<preview>\n{preview}\n...\n</preview>\n"
        f"<instruction>\n"
        f"Notice: User provided a large document payload ({total_chars} characters) that exceeds direct context threshold.\n"
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
        preview_chars: int = PREVIEW_MAX_CHARS,
        ttl_seconds: float = SPILLED_FILE_TTL_SECONDS,
    ) -> None:
        self.max_chars = max_chars
        self.preview_chars = preview_chars
        self.ttl_seconds = ttl_seconds

    def guard_and_spill_query(
        self,
        query: MultimodalQuery,
        workspace_dir: str | Path | None = None,
        session_id: str | None = None,
    ) -> tuple[MultimodalQuery, bool, SpilloverMetadata | None]:
        """Inspect inbound query for context bomb conditions.

        If total character length exceeds max_chars, transparently saves payload
        to sandbox workspace file and returns a transformed query with structured reference.
        """
        raw_text = extract_text_from_query(query)
        total_chars = len(raw_text)

        if total_chars <= self.max_chars:
            return query, False, None

        sha256_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()[:16]
        preview = raw_text[: self.preview_chars].strip()

        # Resolve destination storage root
        if workspace_dir:
            base_dir = Path(workspace_dir).resolve()
            spill_dir = base_dir / SPILLED_DIR_NAME
            rel_file_path = f"{SPILLED_DIR_NAME}/payload_{sha256_hash}.md"
        else:
            fallback_sid = session_id or "default"
            base_dir = Path("/tmp/myrm_spillover").resolve() / fallback_sid
            spill_dir = base_dir
            rel_file_path = str(spill_dir / f"payload_{sha256_hash}.md")

        spill_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(spill_dir, DIR_PERMISSIONS)
        except OSError:
            pass

        target_file = spill_dir / f"payload_{sha256_hash}.md"
        # Anti-directory-traversal security verification
        try:
            target_file.resolve().relative_to(spill_dir.resolve())
        except ValueError as err:
            logger.error("Security violation: spillover path escaped target dir: %s", target_file)
            raise PermissionError("Path traversal violation in spillover directory") from err

        # Idempotent atomic write
        if not target_file.exists():
            tmp_file = target_file.with_suffix(".tmp")
            tmp_file.write_text(raw_text, encoding="utf-8")
            try:
                os.chmod(tmp_file, FILE_PERMISSIONS)
            except OSError:
                pass
            tmp_file.replace(target_file)
            logger.info(
                "ContextBombDefenseService spilled large payload: chars=%d sha256=%s path=%s",
                total_chars,
                sha256_hash,
                rel_file_path,
            )

        metadata = SpilloverMetadata(
            sha256=sha256_hash,
            file_path=rel_file_path,
            total_chars=total_chars,
            preview=preview,
        )

        prompt_block = build_spillover_prompt_block(
            file_path=rel_file_path,
            total_chars=total_chars,
            sha256=sha256_hash,
            preview=preview,
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
                    # Skip additional text blocks if merged
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
        now = time.time()
        cutoff = now - effective_ttl
        purged_count = 0

        target_dirs: list[Path] = []
        if workspace_dir:
            spill_dir = (Path(workspace_dir) / SPILLED_DIR_NAME).resolve()
            if spill_dir.exists():
                target_dirs.append(spill_dir)
        fallback_dir = Path("/tmp/myrm_spillover").resolve()
        if fallback_dir.exists():
            target_dirs.append(fallback_dir)

        for s_dir in target_dirs:
            if not s_dir.exists():
                continue
            for entry in s_dir.rglob("payload_*.md"):
                try:
                    mtime = entry.stat().st_mtime
                    if mtime < cutoff:
                        entry.unlink(missing_ok=True)
                        purged_count += 1
                except OSError as err:
                    logger.debug("Failed cleaning stale spillover file %s: %s", entry, err)

        if purged_count > 0:
            logger.info("ContextBombDefenseService swept %d stale spillover files", purged_count)
        return purged_count


_GLOBAL_CONTEXT_BOMB_GUARD = ContextBombDefenseService()


def get_context_bomb_defense_service() -> ContextBombDefenseService:
    """Return default singleton ContextBombDefenseService."""
    return _GLOBAL_CONTEXT_BOMB_GUARD
