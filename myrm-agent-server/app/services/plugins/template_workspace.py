"""Template workspace files of a plugin expert (business layer).

An expert package can ship starter files (``ai.myrm/workspace/``). They are stored
on the imported expert as ``engine_params["template_workspace_files"]`` (text, or
``base64:``-prefixed for binary content), bounded by the packaging capacity
ceilings, and written into a session workspace the first time that session starts.

[INPUT]
- myrm_agent_harness.agent.plugins.rules::MAX_TEMPLATE_FILE_BYTES, MAX_TOTAL_TEMPLATE_BYTES
  (POS: capacity ceilings shared with the exporter.)

[OUTPUT]
- TEMPLATE_FILES_KEY: ``engine_params`` key that stores the files.
- encode_template_files: raw package files -> storable ``{path: text|base64:...}`` + skipped files.
- decode_template_files: stored files -> raw bytes (export direction).
- materialize_template_workspace_files: safely write stored files into a workspace directory.

[POS]
Single owner of the stored template-file format, shared by import, export, preview
diagnostics and workspace materialization.
"""

from __future__ import annotations

import base64
import binascii
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from myrm_agent_harness.agent.plugins.rules import MAX_TEMPLATE_FILE_BYTES, MAX_TOTAL_TEMPLATE_BYTES

logger = logging.getLogger(__name__)

__all__ = [
    "OVERSIZED_FILE",
    "TEMPLATE_FILES_KEY",
    "TOTAL_SIZE_EXCEEDED",
    "EncodedTemplates",
    "decode_template_files",
    "encode_template_files",
    "materialize_template_workspace_files",
]

TEMPLATE_FILES_KEY: Final = "template_workspace_files"
OVERSIZED_FILE: Final = "oversized_file"
TOTAL_SIZE_EXCEEDED: Final = "total_size_exceeded"
_BASE64_PREFIX: Final = "base64:"


@dataclass(frozen=True)
class EncodedTemplates:
    """Storable template files plus the files that did not fit the capacity ceilings."""

    files: dict[str, str]
    skipped: tuple[tuple[str, str], ...]  # (path, OVERSIZED_FILE | TOTAL_SIZE_EXCEEDED)


def encode_template_files(files: Mapping[str, bytes]) -> EncodedTemplates:
    """Encode package files for storage; files over a ceiling are skipped, not truncated.

    A file that would push the running total over the ceiling is skipped but later,
    smaller files can still fit, so preview diagnostics and persistence agree.
    """
    encoded: dict[str, str] = {}
    skipped: list[tuple[str, str]] = []
    total = 0
    for rel_path, content in files.items():
        size = len(content)
        if size > MAX_TEMPLATE_FILE_BYTES:
            logger.warning("Skipping oversized template file %r (%d bytes, max %d)", rel_path, size, MAX_TEMPLATE_FILE_BYTES)
            skipped.append((rel_path, OVERSIZED_FILE))
            continue
        if total + size > MAX_TOTAL_TEMPLATE_BYTES:
            logger.warning("Skipping template file %r: total would exceed %d bytes", rel_path, MAX_TOTAL_TEMPLATE_BYTES)
            skipped.append((rel_path, TOTAL_SIZE_EXCEEDED))
            continue
        total += size
        try:
            encoded[rel_path] = content.decode("utf-8")
        except UnicodeDecodeError:
            encoded[rel_path] = _BASE64_PREFIX + base64.b64encode(content).decode("ascii")
    return EncodedTemplates(files=encoded, skipped=tuple(skipped))


def decode_template_files(stored: Mapping[str, object]) -> dict[str, bytes]:
    """Decode stored template files back to bytes; malformed entries are dropped."""
    decoded: dict[str, bytes] = {}
    for rel_path, content in stored.items():
        if not isinstance(rel_path, str) or not rel_path.strip() or not isinstance(content, str):
            continue
        raw = _decode_content(content)
        if raw is not None:
            decoded[rel_path] = raw
    return decoded


def _decode_content(content: str) -> bytes | None:
    if not content.startswith(_BASE64_PREFIX):
        return content.encode("utf-8")
    try:
        return base64.b64decode(content[len(_BASE64_PREFIX) :], validate=True)
    except (binascii.Error, ValueError):
        return None


def materialize_template_workspace_files(
    template_files: dict[str, object] | None,
    workspace_dir: str | Path,
) -> list[str]:
    """Write stored template files into ``workspace_dir`` without overwriting anything.

    Only paths that resolve strictly inside the workspace are written (path
    traversal is blocked) and existing files are left untouched. Returns the
    relative paths that were written.
    """
    if not isinstance(template_files, dict) or not template_files:
        return []

    ws_path = Path(workspace_dir).resolve()
    written: list[str] = []

    for raw_rel_path, content in template_files.items():
        if not isinstance(raw_rel_path, str) or not raw_rel_path.strip() or not isinstance(content, str):
            continue
        # Normalize separators and strip leading ones so Windows/posix paths behave alike
        clean_rel_path = raw_rel_path.replace("\\", "/").lstrip("/")
        target_path = (ws_path / clean_rel_path).resolve()
        if not target_path.is_relative_to(ws_path):
            logger.warning("Blocked path traversal in template workspace file: %s", raw_rel_path)
            continue
        if target_path.exists():
            continue
        raw = _decode_content(content)
        if raw is None:
            logger.warning("Skipping template workspace file with invalid base64 content: %s", raw_rel_path)
            continue
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(raw)
        written.append(clean_rel_path)
    return written
