"""Hermes-style deliverable path scanner for channel IM outbound.

Scans assistant reply text (outside fenced/inline code) for workspace-relative
file paths with supported extensions, resolves them within the chat workspace
sandbox, and builds native IM media attachments. Absolute paths are rejected by
the token grammar (first char must be alphanumeric) and by the workspace-root
containment check, so nothing outside the workspace can be attached.

[INPUT]
- Assistant reply markdown/text
- Chat workspace root directory
- deliverable.media::MAX_CHANNEL_ATTACHMENT_BYTES, compress_oversized_image, format_human_size, is_compressible_image (POS: Channel deliverable attachment cap + oversized-image fallback)

[OUTPUT]
- collect_deliverable_paths_from_text(): attachments + stripped text + oversized/compressed notes + tmp paths
- extract_deliverable_path_tokens / resolve_deliverable_path / resolve_chat_workspace_root

[POS]
Channel deliverable attachment mode (Hermes parity). Complements artifact event
collection in deliverable.deep_links.collect_channel_artifacts.
"""

from __future__ import annotations

import mimetypes
import re
from pathlib import Path

from app.channels.types import MediaAttachment, MediaType, guess_media_type

from .media import (
    MAX_CHANNEL_ATTACHMENT_BYTES,
    compress_oversized_image,
    format_human_size,
    is_compressible_image,
)

_DELIVERABLE_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".bmp",
        ".tiff",
        ".svg",
        ".mp4",
        ".mov",
        ".avi",
        ".mkv",
        ".webm",
        ".3gp",
        ".mp3",
        ".m2a",
        ".wav",
        ".ogg",
        ".opus",
        ".m4a",
        ".flac",
        ".pdf",
        ".docx",
        ".doc",
        ".odt",
        ".rtf",
        ".txt",
        ".md",
        ".epub",
        ".xlsx",
        ".xls",
        ".ods",
        ".csv",
        ".tsv",
        ".json",
        ".xml",
        ".yaml",
        ".yml",
        ".pptx",
        ".ppt",
        ".odp",
        ".key",
        ".zip",
        ".tar",
        ".gz",
        ".tgz",
        ".bz2",
        ".xz",
        ".7z",
        ".rar",
        ".html",
        ".htm",
    }
)

_FENCE_RE = re.compile(r"```[\s\S]*?```", re.MULTILINE)
_INLINE_CODE_RE = re.compile(r"`[^`\n]+`")
_PATH_TOKEN_RE = re.compile(
    r"(?P<path>(?:workspace/)?[A-Za-z0-9_][A-Za-z0-9_./-]*\.[A-Za-z0-9]{1,12})"
)


def _strip_code_regions(text: str) -> str:
    without_fences = _FENCE_RE.sub(" ", text)
    return _INLINE_CODE_RE.sub(" ", without_fences)


def _normalize_token(raw: str) -> str:
    return raw.strip().strip(".,;:!?)\"'")


def _is_deliverable_extension(path: str) -> bool:
    return Path(path).suffix.lower() in _DELIVERABLE_EXTENSIONS


def resolve_deliverable_path(token: str, workspace_root: str | None) -> Path | None:
    """Resolve a scanned path token to an on-disk file within workspace_root."""
    cleaned = _normalize_token(token)
    if not cleaned or not _is_deliverable_extension(cleaned):
        return None
    if not workspace_root:
        return None

    if cleaned.startswith("workspace/"):
        rel = cleaned[len("workspace/") :]
    else:
        rel = cleaned

    candidate = Path(workspace_root) / rel

    try:
        resolved = candidate.resolve()
        root = Path(workspace_root).resolve()
        resolved.relative_to(root)
    except (OSError, ValueError):
        return None

    if not resolved.is_file():
        return None

    return resolved


def extract_deliverable_path_tokens(text: str) -> list[str]:
    """Extract candidate deliverable path tokens from non-code regions."""
    scan_surface = _strip_code_regions(text)
    found: list[str] = []
    seen: set[str] = set()
    for match in _PATH_TOKEN_RE.finditer(scan_surface):
        token = _normalize_token(match.group("path"))
        if not token or token in seen:
            continue
        seen.add(token)
        found.append(token)
    return found


def collect_deliverable_paths_from_text(
    text: str,
    *,
    workspace_root: str | None,
    existing_filenames: set[str] | None = None,
) -> tuple[
    str,
    list[MediaAttachment],
    list[tuple[str, str]],
    list[tuple[str, str]],
    list[str],
]:
    """Scan reply text, attach deliverable files, and strip matched path tokens.

    Returns ``(stripped_text, attachments, oversized_notes, compressed_notes, tmp_paths)``:
    - oversized_notes: ``(filename, size_str)`` pairs that exceed the channel cap
      and could not be delivered as attachments.
    - compressed_notes: ``(filename, size_str)`` pairs whose oversized images were
      compressed and sent as attachments instead.
    - tmp_paths: temp files produced by image compression, cleaned by caller.
    """
    tokens = extract_deliverable_path_tokens(text)
    if not tokens:
        return text, [], [], [], []

    attachments: list[MediaAttachment] = []
    oversized_notes: list[tuple[str, str]] = []
    compressed_notes: list[tuple[str, str]] = []
    tmp_paths: list[str] = []
    used_filenames = set(existing_filenames or ())
    stripped = text

    for token in tokens:
        resolved = resolve_deliverable_path(token, workspace_root)
        if resolved is None:
            continue
        try:
            size = resolved.stat().st_size
        except OSError:
            continue
        if size == 0:
            continue

        filename = resolved.name
        if filename in used_filenames:
            stripped = stripped.replace(token, "")
            continue

        if size > MAX_CHANNEL_ATTACHMENT_BYTES:
            stripped = stripped.replace(token, "")
            if is_compressible_image(filename):
                compressed = compress_oversized_image(
                    resolved,
                    max_bytes=MAX_CHANNEL_ATTACHMENT_BYTES,
                )
                if compressed is not None:
                    tmp_paths.append(str(compressed))
                    mime = (
                        mimetypes.guess_type(str(compressed))[0]
                        or "application/octet-stream"
                    )
                    attachments.append(
                        MediaAttachment(
                            media_type=MediaType.IMAGE,
                            path=str(compressed),
                            filename=Path(filename).stem + Path(str(compressed)).suffix,
                            mime_type=mime,
                        )
                    )
                    compressed_notes.append((filename, format_human_size(size)))
                    used_filenames.add(filename)
                    continue
            oversized_notes.append((filename, format_human_size(size)))
            continue

        mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        attachments.append(
            MediaAttachment(
                media_type=guess_media_type(filename, mime),
                path=str(resolved),
                filename=filename,
                mime_type=mime,
            )
        )
        used_filenames.add(filename)
        stripped = stripped.replace(token, "")

    return stripped.strip(), attachments, oversized_notes, compressed_notes, tmp_paths


async def resolve_chat_workspace_root(chat_id: str) -> str | None:
    """Load workspace_dir for a chat from DB."""
    try:
        from sqlalchemy import select

        from app.database.connection import get_session
        from app.database.models.chat import Chat

        async with get_session() as db:
            result = await db.execute(
                select(Chat.workspace_dir).where(Chat.id == chat_id)
            )
            workspace_dir = result.scalar_one_or_none()
            if isinstance(workspace_dir, str) and workspace_dir.strip():
                return workspace_dir.strip()
    except Exception:
        return None
    return None
