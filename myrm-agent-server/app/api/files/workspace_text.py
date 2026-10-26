"""Workspace text editor API: versioned read, compare-and-swap save, save as copy.

[INPUT]
- app.api.files.workspace_ops::resolve_workspace, validate_target, dedup_filename (POS: workspace boundary,
  dangerous-path and sensitive-file guards shared with the other write endpoints)
- app.services.files.text_edit_io (POS: byte-exact, versioned text file I/O)
- app.core.utils.errors::validation_error, not_found_error, conflict_error, internal_error
- app.core.utils.response_utils::success_response

[OUTPUT]
- GET  /browse/text       — Read a text file with its content version and an editable / read-only verdict
- PUT  /browse/text       — Save against ``base_version``; 409 when the file changed since it was read
- POST /browse/text/copy  — Write the edited text to a new sibling file ("name (1).ext")

[POS]
Human-editor counterpart of the agent's read/version gates. Bodies carry the text as base64
(``content_b64``) so request-text sanitising can never rewrite file content. Every refusal carries a
machine-readable ``reason`` detail (``version_conflict``, ``write_blocked``, ``binary``, ...) that the
frontend localises; the English ``message`` is a fallback for logs.
"""

import asyncio
import base64
import logging
import os

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.api.files.workspace_ops import dedup_filename, resolve_workspace, validate_target
from app.core.utils.errors import conflict_error, internal_error, not_found_error, validation_error
from app.core.utils.response_utils import success_response
from app.schemas.responses import ErrorDetail
from app.services.files.text_edit_io import (
    EDITABLE_MAX_BYTES,
    InvalidContent,
    NotEditable,
    TextSnapshot,
    VersionConflict,
    WriteBlocked,
    WriteOutcome,
    create_text_file_exclusive,
    read_text_snapshot,
    text_style_of,
    write_text_if_version,
)

logger = logging.getLogger(__name__)

router = APIRouter()

_MAX_CONTENT_B64_CHARS = 4 * ((EDITABLE_MAX_BYTES + 2) // 3)
_COPY_NAME_ATTEMPTS = 5


class TextSaveRequest(BaseModel):
    workspace: str = Field(..., description="Workspace root path")
    path: str = Field(..., description="File to save (absolute or relative to the workspace)")
    content_b64: str = Field(..., max_length=_MAX_CONTENT_B64_CHARS, description="New text, UTF-8 then base64")
    base_version: str = Field(..., pattern=r"^[0-9a-f]{64}$", description="Version the edit started from")


class TextCopyRequest(BaseModel):
    workspace: str = Field(..., description="Workspace root path")
    path: str = Field(..., description="File the copy is made next to (also donates line endings and BOM)")
    content_b64: str = Field(..., max_length=_MAX_CONTENT_B64_CHARS, description="Text to store, UTF-8 then base64")


def _reason(reason: str, *extra: ErrorDetail) -> list[ErrorDetail]:
    return [ErrorDetail(field="reason", issue=reason), *extra]


def _resolve_file(workspace: str, path: str) -> str:
    """Workspace-guarded absolute path of an existing regular file."""
    ws = resolve_workspace(workspace)
    raw = path if os.path.isabs(path) else os.path.join(ws, path)
    target = validate_target(raw, ws)
    if os.path.isdir(target):
        raise validation_error("Not a file", details=_reason("not_a_file"))
    if not os.path.isfile(target):
        raise not_found_error("File", details=_reason("not_found"))
    return target


def _decode_content(content_b64: str) -> str:
    try:
        return base64.b64decode(content_b64, validate=True).decode("utf-8")
    except ValueError as exc:  # binascii.Error and UnicodeDecodeError are both ValueErrors
        raise validation_error("Content is not base64-encoded UTF-8", details=_reason("invalid_content")) from exc


def _snapshot_payload(snapshot: TextSnapshot, target: str) -> dict[str, object]:
    return {
        "path": target,
        "name": os.path.basename(target),
        "content": snapshot.content,
        "version": snapshot.version,
        "size": snapshot.size,
        "editable": snapshot.editable,
        "readonly_reason": snapshot.readonly_reason,
        "truncated": snapshot.truncated,
    }


def _written_payload(target: str, outcome: WriteOutcome) -> dict[str, object]:
    return {
        "path": target,
        "name": os.path.basename(target),
        "version": outcome.version,
        "size": outcome.size,
        "changed": outcome.changed,
    }


def _invalid_content_error(exc: InvalidContent) -> Exception:
    reason = "content_too_large" if exc.issue == "too_large" else "invalid_content"
    return validation_error("Content cannot be stored as a text file", details=_reason(reason))


@router.get("/browse/text", response_model=None)
async def read_text_file(
    workspace: str = Query(..., description="Workspace root path"),
    path: str = Query(..., description="File path (absolute or relative to the workspace)"),
) -> JSONResponse:
    """Read a text file for editing.

    Files the editor cannot round-trip byte-exactly (binary, non-UTF-8, mixed line endings, over 1 MiB) are
    returned read-only with the reason; only the first 1 MiB of an oversized file is returned.
    """
    target = _resolve_file(workspace, path)
    try:
        snapshot = await asyncio.to_thread(read_text_snapshot, target)
    except FileNotFoundError as exc:
        raise not_found_error("File", details=_reason("not_found")) from exc
    except PermissionError as exc:
        raise validation_error("Permission denied", details=_reason("read_blocked")) from exc
    return success_response(data=_snapshot_payload(snapshot, target))


@router.put("/browse/text", response_model=None)
async def save_text_file(body: TextSaveRequest) -> JSONResponse:
    """Save edited text over a file, only when it is still the version the edit started from."""
    target = _resolve_file(body.workspace, body.path)
    text = _decode_content(body.content_b64)
    try:
        outcome = await asyncio.to_thread(write_text_if_version, target, text, body.base_version)
    except VersionConflict as exc:
        raise conflict_error(
            "File changed since it was opened",
            details=_reason("version_conflict", ErrorDetail(field="current_version", issue=exc.current_version)),
        ) from exc
    except NotEditable as exc:
        raise validation_error("File cannot be edited", details=_reason(exc.reason)) from exc
    except InvalidContent as exc:
        raise _invalid_content_error(exc) from exc
    except (WriteBlocked, PermissionError) as exc:
        raise validation_error("File is read-only or in use", details=_reason("write_blocked")) from exc
    except FileNotFoundError as exc:
        raise not_found_error("File", details=_reason("not_found")) from exc
    except OSError as exc:
        raise internal_error(operation="Save text file", exception=exc) from exc
    return success_response(data=_written_payload(target, outcome))


@router.post("/browse/text/copy", response_model=None)
async def save_text_copy(body: TextCopyRequest) -> JSONResponse:
    """Write edited text to a new file next to the original, never overwriting anything."""
    source = _resolve_file(body.workspace, body.path)
    text = _decode_content(body.content_b64)
    ws = resolve_workspace(body.workspace)
    directory, name = os.path.split(source)
    style = await asyncio.to_thread(text_style_of, source)
    for _ in range(_COPY_NAME_ATTEMPTS):
        destination = validate_target(os.path.join(directory, dedup_filename(directory, name)), ws)
        try:
            outcome = await asyncio.to_thread(create_text_file_exclusive, destination, text, style)
        except FileExistsError:
            continue  # another writer took the name between the check and the create: pick the next one
        except InvalidContent as exc:
            raise _invalid_content_error(exc) from exc
        except PermissionError as exc:
            raise validation_error("Cannot write next to the original", details=_reason("write_blocked")) from exc
        except OSError as exc:
            raise internal_error(operation="Save text copy", exception=exc) from exc
        return success_response(data=_written_payload(destination, outcome))
    raise conflict_error("Could not find a free file name", details=_reason("name_unavailable"))
