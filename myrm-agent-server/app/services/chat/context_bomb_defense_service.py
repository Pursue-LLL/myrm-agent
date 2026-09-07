"""Context bomb defense and transparent file spillover service.

[INPUT]
- hashlib (POS: SHA-256 generation)
- pathlib.Path (POS: filesystem path operations)
- app.config.settings (POS: workspace and base path configurations)

[OUTPUT]
- ContextBombDefenseService: High-volume message content detector, file spillover engine and prompt injector.
- SpilloverPayloadResult: Dataclass containing spillover status, file path, summary, and hash metadata.

[POS]
Server-side message body cap defense layer.
Protects LLM inference context from 'context bomb' attacks or accidental massive pastes (>16,000 chars)
by automatically offloading raw text into user sandbox filesystem (`.myrm/spillover/`)
and injecting structured `<file_spillover path="..." chars="..." digest="..." />` tags.
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Final

logger = logging.getLogger(__name__)

# Rigid security boundary threshold (aligned with Hermes bot_mode_dm and industrial standards)
MESSAGE_MAX_CHARS: Final[int] = 16_000
# Retention period for transient spillover files (24 hours)
SPILLED_FILE_TTL_SECONDS: Final[int] = 86_400
# Maximum length for contextual inline summary snippet
SUMMARY_HEAD_CHARS: Final[int] = 300


@dataclass(slots=True, frozen=True)
class SpilloverPayloadResult:
    is_spilled: bool
    processed_content: str
    original_char_count: int
    spillover_path: str | None = None
    content_sha256: str | None = None


class ContextBombDefenseService:
    """Service to detect ultra-long incoming message texts, offload them to sandbox files,

    and assemble prompt-cache friendly structural references.
    """

    @staticmethod
    def get_spillover_dir(workspace_root: Path | str | None = None) -> Path:
        """Resolve and initialize the transient spillover storage directory.

        Ensures POSIX 0o700 permission boundary for isolation.
        """
        if workspace_root is None:
            # Fallback to local default workspace / state dir
            base_dir = Path.home() / ".myrm" / "spillover"
        else:
            base_dir = Path(workspace_root) / ".myrm" / "spillover"

        base_dir.mkdir(parents=True, exist_ok=True)
        try:
            # Enforce 0o700 permissions on UNIX environments
            os.chmod(base_dir, 0o700)
        except OSError:
            pass  # Windows or restricted filesystems

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
        """Inspect message text length and transparently spill over to file if exceeding cap.

        Args:
            content: Raw user or incoming channel message text.
            chat_id: Identifier for current conversation session.
            workspace_root: Path to the target sandbox workspace directory.
            max_chars: Upper boundary threshold for inline text.

        Returns:
            SpilloverPayloadResult with processed content (either original or structured prompt).
        """
        char_count = len(content)
        if char_count <= max_chars:
            return SpilloverPayloadResult(
                is_spilled=False,
                processed_content=content,
                original_char_count=char_count,
            )

        # Content exceeds boundary: perform transparent file spillover
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        file_id = uuid.uuid4().hex[:12]
        file_name = f"spillover_{file_id}.md"

        target_dir = cls.get_spillover_dir(workspace_root)
        target_file = target_dir / file_name

        try:
            target_file.write_text(content, encoding="utf-8")
            try:
                os.chmod(target_file, 0o600)
            except OSError:
                pass
        except Exception as e:
            logger.error("Failed to write transient spillover file: %s", e, exc_info=True)
            # If disk write fails, fall back to safe head truncation warning
            truncated = content[:max_chars]
            return SpilloverPayloadResult(
                is_spilled=False,
                processed_content=truncated + f"\n\n[System Warning: Text truncated to {max_chars} chars due to file spillover write failure]",
                original_char_count=char_count,
            )

        # Formulate structured reference and prompt guidance
        head_snippet = content[:SUMMARY_HEAD_CHARS].replace("\n", " ").strip()
        relative_or_abs_path = str(target_file.resolve())

        prompt_guidance = (
            f"[User submitted a large document ({char_count:,} characters). "
            f"To protect inference context window and ensure prompt cache efficiency, the full content has been saved to: `{relative_or_abs_path}`]\n\n"
            f"<file_spillover path=\"{relative_or_abs_path}\" chars=\"{char_count}\" digest=\"{digest}\" />\n\n"
            f"Preview of document head (first {SUMMARY_HEAD_CHARS} chars):\n"
            f"> \"{head_snippet}...\"\n\n"
            f"Instruction: Use the `read_file` tool to inspect full content or specific sections as needed."
        )

        logger.info(
            "Context bomb mitigated: spilled %d chars to %s (digest=%s) for chat_id=%s",
            char_count,
            relative_or_abs_path,
            digest[:8],
            chat_id or "unknown",
        )

        return SpilloverPayloadResult(
            is_spilled=True,
            processed_content=prompt_guidance,
            original_char_count=char_count,
            spillover_path=relative_or_abs_path,
            content_sha256=digest,
        )

    @classmethod
    def cleanup_transient_spillover_cache(
        cls,
        workspace_root: Path | str | None = None,
        ttl_seconds: int = SPILLED_FILE_TTL_SECONDS,
    ) -> int:
        """Scan and purge expired transient spillover files older than TTL (24 hours).

        Returns:
            Number of removed stale files.
        """
        target_dir = cls.get_spillover_dir(workspace_root)
        if not target_dir.exists():
            return 0

        now = time.time()
        purged_count = 0

        try:
            for item in target_dir.iterdir():
                if not item.is_file() or not item.name.startswith("spillover_"):
                    continue
                try:
                    mtime = item.stat().st_mtime
                    if now - mtime > ttl_seconds:
                        item.unlink(missing_ok=True)
                        purged_count += 1
                except OSError as err:
                    logger.warning("Error purging stale spillover file %s: %s", item, err)
        except Exception as e:
            logger.error("Failed during transient spillover cleanup: %s", e)

        if purged_count > 0:
            logger.info("Purged %d expired transient spillover files from %s", purged_count, target_dir)

        return purged_count
