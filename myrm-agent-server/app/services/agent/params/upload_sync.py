"""
[INPUT]
app.core.storage.service::FilesService (POS: file storage service)

[OUTPUT]
sync_uploaded_files_to_workspace: copy large uploaded files to workspace
inject_uploaded_files_into_query: append file paths to the user query

[POS]
Uploaded-file workspace sync. Copies large attached files from StorageProvider
to the agent workspace so code execution tools (bash, file_read) can access them.
Only syncs files exceeding the inline context limit (100 KB).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from xml.sax.saxutils import quoteattr

from .models import MultimodalQuery

logger = logging.getLogger(__name__)

_SYNC_THRESHOLD_BYTES = 100 * 1024  # 100 KB — matches _MENTION_MAX_INLINE_BYTES
_UPLOADED_DIR_NAME = "_uploaded"
_MAX_SYNC_FILES = 10
_MAX_SYNC_TOTAL_BYTES = 50 * 1024 * 1024  # 50 MB per chat session


async def sync_uploaded_files_to_workspace(
    file_ids: list[str],
    workspace_dir: str,
) -> list[tuple[str, str]]:
    """Copy uploaded files from StorageProvider to ``{workspace_dir}/_uploaded/``.

    Only copies files whose size exceeds *_SYNC_THRESHOLD_BYTES*.
    Returns a list of ``(filename, workspace_relative_path)`` tuples for
    successfully synced files.
    """
    from app.core.storage import files_service

    uploaded_dir = os.path.join(workspace_dir, _UPLOADED_DIR_NAME)
    synced: list[tuple[str, str]] = []
    total_bytes = 0

    for file_id in file_ids[:_MAX_SYNC_FILES]:
        try:
            file_meta = await files_service.get_file(file_id)
            if file_meta is None:
                logger.debug("Uploaded file %s not found, skipping sync", file_id)
                continue

            if file_meta.size <= _SYNC_THRESHOLD_BYTES:
                continue

            if total_bytes + file_meta.size > _MAX_SYNC_TOTAL_BYTES:
                logger.warning(
                    "Skipping file %s (%d bytes): would exceed 50 MB sync budget",
                    file_id,
                    file_meta.size,
                )
                continue

            content = await files_service.get_file_content_by_path(file_meta.storage_path)
            if content is None:
                logger.warning("Could not read content for file %s", file_id)
                continue

            os.makedirs(uploaded_dir, exist_ok=True)

            safe_name = _sanitize_filename(file_meta.filename)
            dest_path = os.path.join(uploaded_dir, safe_name)

            # Avoid overwriting existing files from other turns
            if os.path.exists(dest_path):
                stem = Path(safe_name).stem
                suffix = Path(safe_name).suffix
                counter = 1
                while os.path.exists(dest_path):
                    dest_path = os.path.join(uploaded_dir, f"{stem}_{counter}{suffix}")
                    counter += 1
                safe_name = os.path.basename(dest_path)

            with open(dest_path, "wb") as f:
                f.write(content)

            rel_path = os.path.join(_UPLOADED_DIR_NAME, safe_name)
            synced.append((file_meta.filename, rel_path))
            total_bytes += file_meta.size
            logger.info("Synced uploaded file %s → %s (%d bytes)", file_id, rel_path, file_meta.size)

        except Exception:
            logger.warning("Failed to sync uploaded file %s", file_id, exc_info=True)

    return synced


_RAG_DOC_EXTENSIONS = frozenset({".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt"})
_RAG_TEXT_THRESHOLD = 100 * 1024


def _should_use_rag(original_name: str, rel_path: str, workspace_dir: str) -> bool:
    """Determine if a synced file should be ingested into wiki for RAG retrieval."""
    ext = os.path.splitext(original_name)[1].lower()
    if ext not in _RAG_DOC_EXTENSIONS:
        return False
    full_path = os.path.join(workspace_dir, rel_path)
    try:
        return os.path.getsize(full_path) > _RAG_TEXT_THRESHOLD
    except OSError:
        return False


def inject_uploaded_files_into_query(
    query: MultimodalQuery,
    synced_files: list[tuple[str, str]],
    workspace_dir: str = "",
) -> MultimodalQuery:
    """Append uploaded-file workspace paths to the user query.

    Large documents (PDF/DOCX >100KB) are tagged for wiki RAG ingestion
    so the Agent uses ``wiki_ingest`` + ``wiki_query`` instead of reading
    the entire file into the prompt.
    """
    if not synced_files:
        return query

    direct_lines: list[str] = []
    rag_lines: list[str] = []

    for original_name, rel_path in synced_files:
        if workspace_dir and _should_use_rag(original_name, rel_path, workspace_dir):
            rag_lines.append(
                f"  <file name={quoteattr(original_name)} workspace_path={quoteattr(rel_path)}"
                f' action="wiki_ingest_then_query"/>'
            )
        else:
            direct_lines.append(
                f"  <file name={quoteattr(original_name)} workspace_path={quoteattr(rel_path)}/>"
            )

    parts: list[str] = []
    if direct_lines:
        parts.append("<uploaded_files_in_workspace>")
        parts.extend(direct_lines)
        parts.append("</uploaded_files_in_workspace>")
    if rag_lines:
        parts.append("<large_documents_for_knowledge_base>")
        parts.extend(rag_lines)
        parts.append(
            "  Use wiki_ingest_tool to ingest these large documents, "
            "then use wiki_query_tool to answer questions about them. "
            "Do NOT read the entire file into the conversation."
        )
        parts.append("</large_documents_for_knowledge_base>")

    if not parts:
        return query

    context = "\n".join(parts)

    if isinstance(query, str):
        return f"{query}\n\n{context}"
    for part in query:
        if part.get("type") == "text" and isinstance(part.get("text"), str):
            part["text"] = str(part["text"]) + f"\n\n{context}"
            return query
    query.append({"type": "text", "text": context})
    return query


def _sanitize_filename(filename: str) -> str:
    """Remove path separators and null bytes from a filename."""
    name = os.path.basename(filename)
    name = name.replace("\0", "").replace("/", "_").replace("\\", "_")
    return name or "unnamed_file"
