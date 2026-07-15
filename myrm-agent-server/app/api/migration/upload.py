"""Cloud migration ZIP upload endpoint.

[INPUT]
Multipart/form-data ZIP file containing competitor AI assistant data.

[OUTPUT]
DiscoveryResponse with detected sources from the uploaded archive.

[POS]
Cloud/SaaS migration bridge — accepts a user-uploaded ZIP of competitor data,
safely extracts to a temporary directory, runs existing source probes, and
returns the same DiscoveryResponse used by the local discover endpoint.
Enables three-deployment parity for the Migration Wizard.
Also detects ChatGPT export ZIPs (containing conversations.json) and returns
them as a chatgpt source for the import path.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import tempfile
import zipfile

from fastapi import APIRouter, HTTPException, UploadFile

from app.api.migration.discovery import (
    DiscoveredFileResponse,
    DiscoveryResponse,
    ExternalSourceResponse,
    _to_response,
)
from app.services.migration.source_discovery import discover_external_sources

router = APIRouter(prefix="/migration", tags=["migration"])

MAX_ZIP_BYTES = 50 * 1024 * 1024  # 50 MB
MAX_EXTRACTED_FILES = 5000


def _is_safe_path(member_name: str) -> bool:
    """Reject path-traversal attempts (../ or absolute paths)."""
    normalized = os.path.normpath(member_name)
    return not normalized.startswith(("../", "..\\", "/")) and ".." not in normalized.split(os.sep)


_CHATGPT_HEADER_PROBE_BYTES = 4096


def _detect_chatgpt_zip(tmpdir: str) -> str | None:
    """Return path to conversations.json if this looks like a ChatGPT export ZIP."""

    top_level = os.path.join(tmpdir, "conversations.json")
    if os.path.isfile(top_level) and _is_chatgpt_conversations_file(top_level):
        return top_level

    for dirpath, _dirs, files in os.walk(tmpdir):
        for fname in files:
            if fname == "conversations.json":
                fpath = os.path.join(dirpath, fname)
                if _is_chatgpt_conversations_file(fpath):
                    return fpath
    return None


def _is_chatgpt_conversations_file(path: str) -> bool:
    """Probe file header for ChatGPT conversation structure markers."""

    try:
        with open(path, "rb") as f:
            header = f.read(_CHATGPT_HEADER_PROBE_BYTES)
        return b'"mapping"' in header and b'"current_node"' in header
    except OSError:
        return False


@router.post("/upload", response_model=DiscoveryResponse)
async def upload_migration_zip(file: UploadFile) -> DiscoveryResponse:
    """Accept a ZIP of competitor data and return discovered sources.

    Cloud users package their local competitor directories (e.g. ~/.hermes,
    ~/.openclaw) into a ZIP and upload here. The server extracts to a temp
    directory, runs the same probes used by GET /migration/discover, and
    returns matching results so the frontend can continue with the standard
    Wizard flow.

    Also detects ChatGPT export ZIPs (containing conversations.json) and
    returns a synthetic chatgpt source so the frontend can proceed with import.
    """

    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only .zip files are accepted")

    content = await file.read()
    if len(content) > MAX_ZIP_BYTES:
        raise HTTPException(status_code=413, detail=f"File exceeds {MAX_ZIP_BYTES // (1024 * 1024)} MB limit")

    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile as exc:
        raise HTTPException(status_code=400, detail="Invalid ZIP file") from exc

    members = archive.infolist()
    if len(members) > MAX_EXTRACTED_FILES:
        archive.close()
        raise HTTPException(status_code=400, detail=f"ZIP contains too many files (max {MAX_EXTRACTED_FILES})")

    unsafe = [m.filename for m in members if not _is_safe_path(m.filename)]
    if unsafe:
        archive.close()
        raise HTTPException(status_code=400, detail="ZIP contains unsafe paths")

    tmpdir = tempfile.mkdtemp(prefix="myrm_migration_")
    archive.extractall(tmpdir)
    archive.close()

    chatgpt_path = _detect_chatgpt_zip(tmpdir)
    if chatgpt_path:
        return _build_chatgpt_discovery(chatgpt_path)

    result = discover_external_sources(home_dir=tmpdir)

    if not result.sources:
        shutil.rmtree(tmpdir, ignore_errors=True)
        return DiscoveryResponse(sources=[], scan_path="upload", available=True)

    return DiscoveryResponse(
        sources=[_to_response(s) for s in result.sources],
        scan_path="upload",
        available=True,
    )


def _build_chatgpt_discovery(conversations_path: str) -> DiscoveryResponse:
    """Build a discovery response for a ChatGPT export ZIP."""

    count = 0
    size_bytes = 0
    try:
        size_bytes = os.path.getsize(conversations_path)
        with open(conversations_path, encoding="utf-8") as f:
            data = json.load(f)
        count = len(data) if isinstance(data, list) else 0
    except (OSError, json.JSONDecodeError):
        pass

    source = ExternalSourceResponse(
        competitor="chatgpt",
        root=conversations_path,
        confidence="high",
        files=[DiscoveredFileResponse(path=conversations_path, kind="conversations_json", size_bytes=size_bytes)],
        memory_count_estimate=count,
    )
    return DiscoveryResponse(sources=[source], scan_path="upload", available=True)
