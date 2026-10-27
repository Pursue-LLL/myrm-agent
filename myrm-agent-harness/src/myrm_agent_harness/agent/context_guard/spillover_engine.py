"""Detect oversized message payloads and spill them to referenced workspace files.

[INPUT]
- contextlib::contextlib (POS: Python 上下文管理器标准库)
- hashlib::hashlib (POS: Python 内容哈希标准库)
- pathlib::Path (POS: Python 面向对象路径标准库)
- uuid::uuid4 (POS: Python UUID 生成标准库)
- agent.context_guard.types::ContextGuardConfig, SpilloverPayload, SpilloverResult,
  estimate_token_pressure (POS: 上下文守卫数据模型与 token 压力估算层)
- utils.logger_utils::get_agent_logger (POS: 框架统一日志获取层)

[OUTPUT]
- SpilloverEngine.process_content: SpilloverResult, carrying either the original content
  untouched or a stub (start and end preview, workspace-relative path, counts, digest)
  plus SpilloverPayload metadata

[POS]
Transparent-overflow engine of the context guard subsystem. The file is named after the
content hash and written with a temp-file rename: readers never observe a partial payload,
spilling the same text again reuses the file, and the stub is byte-identical every time, so
a live run and a stored conversation can both carry it. The directory ignores itself
(``.gitignore``) because the workspace may be a project under version control.
Framework-level: keeps the run inside the context window without dropping information, so
the model can read the file back when it needs the detail.
"""

from __future__ import annotations

import contextlib
import hashlib
from pathlib import Path
from uuid import uuid4

from myrm_agent_harness.agent.context_guard.types import (
    ContextGuardConfig,
    SpilloverPayload,
    SpilloverResult,
    estimate_token_pressure,
)
from myrm_agent_harness.utils.logger_utils import get_agent_logger

logger = get_agent_logger(__name__)

# 64 bits of the digest name the file: a kept spill is permanent, so a collision must stay out of reach.
_NAME_DIGEST_CHARS = 16
_IGNORE_FILE_NAME = ".gitignore"


def _render_stub(
    *,
    role: str,
    relative_path: str,
    char_count: int,
    line_count: int,
    estimated_tokens: int,
    digest: str,
    head: str,
    tail: str,
) -> str:
    """The text that takes the place of a spilled payload in the prompt."""
    tail_block = f"<preview_end>\n{tail}\n</preview_end>\n" if tail else ""
    return (
        f'<file_spillover path="{relative_path}" chars="{char_count}" lines="{line_count}" digest="{digest}">\n'
        f"<preview_start>\n{head}\n</preview_start>\n"
        f"{tail_block}"
        f"<instruction>\n"
        f"Notice: The {role} pasted a large text ({char_count:,} characters, ~{estimated_tokens:,} tokens) "
        f"that is saved at '{relative_path}' instead of being inserted here; only its start and end are shown above.\n"
        f"The {role}'s request may be in the part you cannot see. Read the file with file_read_tool before you answer "
        f"(all of it when the request or your answer depends on its content; a line range when the shown parts "
        f"already make the request clear).\n"
        f"If this message holds nothing but the pasted text, the pasted text is the {role}'s request: "
        f"read all of it and do what it asks.\n"
        f"</instruction>\n"
        f"</file_spillover>"
    )


class SpilloverEngine:
    """Detects message body overflow and transparently writes payloads to local disk."""

    def __init__(self, config: ContextGuardConfig | None = None) -> None:
        self.config = config or ContextGuardConfig()

    def process_content(
        self,
        content: str | list[dict[str, object] | str] | dict[str, object],
        *,
        base_dir: Path | str,
        role: str = "user",
        custom_prefix: str = "payload",
        session_id: str | None = None,
    ) -> SpilloverResult:
        """Evaluate message length and adaptive token pressure.

        Spills to workspace disk if character cap OR token pressure cap is breached.
        """
        raw_text = self._extract_text(content)
        char_count = len(raw_text)
        token_pressure = estimate_token_pressure(raw_text)

        if char_count <= self.config.max_message_chars and token_pressure <= self.config.max_token_pressure:
            return SpilloverResult(
                spilled=False,
                sanitized_content=raw_text,
                original_char_count=char_count,
                estimated_tokens=token_pressure,
            )

        # Content exceeds threshold -> create atomic, concurrency-safe spillover file
        root_path = Path(base_dir).expanduser().resolve()
        spillover_dir = root_path / self.config.spillover_dir_name
        spillover_dir.mkdir(parents=True, exist_ok=True)

        # Enforce POSIX 0o700 directory permissions
        with contextlib.suppress(OSError):
            spillover_dir.chmod(0o700)
        self._ignore_directory(spillover_dir)

        sha256 = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
        spill_id = f"{custom_prefix}_{sha256[:_NAME_DIGEST_CHARS]}"
        target_file = spillover_dir / f"{spill_id}.md"

        # Anti-directory-traversal verification
        try:
            target_file.resolve().relative_to(spillover_dir.resolve())
        except ValueError as err:
            logger.error(
                "Security violation: spillover target escaped directory: %s",
                target_file,
            )
            raise PermissionError("Path traversal detected in spillover target file") from err

        self._write_once(target_file, raw_text)

        logger.info(
            "Context bomb mitigated: spilled %d chars (~%d tokens) into %s (sha256=%s)",
            char_count,
            token_pressure,
            target_file,
            sha256[:8],
        )

        relative_path = str(target_file.relative_to(root_path))
        lines = raw_text.count("\n") + 1
        preview_chars = self.config.preview_chars
        head = raw_text[:preview_chars].strip()
        # A text this short has no separate end: it would repeat the start.
        tail = raw_text[-preview_chars:].strip() if preview_chars and char_count > 2 * preview_chars else ""

        payload = SpilloverPayload(
            spill_id=spill_id,
            file_path=str(target_file),
            relative_path=relative_path,
            char_count=char_count,
            line_count=lines,
            estimated_tokens=token_pressure,
            sha256_digest=sha256,
            summary_preview=head,
            original_role=role,
        )

        return SpilloverResult(
            spilled=True,
            sanitized_content=_render_stub(
                role=role,
                relative_path=relative_path,
                char_count=char_count,
                line_count=lines,
                estimated_tokens=token_pressure,
                digest=sha256[:16],
                head=head,
                tail=tail,
            ),
            payload=payload,
            original_char_count=char_count,
            estimated_tokens=token_pressure,
        )

    @staticmethod
    def _ignore_directory(directory: Path) -> None:
        """Make version control skip the directory and everything in it."""
        ignore_file = directory / _IGNORE_FILE_NAME
        if not ignore_file.exists():
            with contextlib.suppress(OSError):
                ignore_file.write_text("*\n", encoding="utf-8")

    @staticmethod
    def _write_once(target_file: Path, text: str) -> None:
        """Write ``text`` to ``target_file`` unless the file already holds it (its name is the content hash)."""
        data = text.encode("utf-8")
        with contextlib.suppress(FileNotFoundError):
            if target_file.stat().st_size == len(data):
                # Spilling the same text again renews the file's age, so a sweeper keeps it for another TTL.
                with contextlib.suppress(OSError):
                    target_file.touch()
                return
        # Atomic, race-condition safe file write with unique temp suffix
        unique_tmp = target_file.with_name(f".tmp_{target_file.stem}_{uuid4().hex[:6]}")
        try:
            unique_tmp.write_bytes(data)
            with contextlib.suppress(OSError):
                unique_tmp.chmod(0o600)
            unique_tmp.replace(target_file)
        finally:
            with contextlib.suppress(OSError):
                unique_tmp.unlink(missing_ok=True)

    @staticmethod
    def _extract_text(
        content: str | list[dict[str, object] | str] | dict[str, object] | object,
    ) -> str:
        """Extract plain text string from str, list, or dict structures."""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    if item.get("type") == "text" and "text" in item:
                        parts.append(str(item["text"]))
                    elif "content" in item and isinstance(item["content"], str):
                        parts.append(item["content"])
            return "\n".join(parts)
        if isinstance(content, dict):
            if "text" in content and isinstance(content["text"], str):
                return content["text"]
            if "content" in content and isinstance(content["content"], str):
                return content["content"]
        return ""
