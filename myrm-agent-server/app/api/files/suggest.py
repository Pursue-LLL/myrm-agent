"""
[INPUT]
myrm_agent_harness.toolkits.filesystem_suggest::suggest_workspace_paths (POS: Workspace path suggestion ranker)
app.services.chat.chat_service::ChatService (POS: Chat metadata and workspace resolver)
app.core.storage::files_service (POS: Stored file metadata service)

[OUTPUT]
GET /api/v1/files/suggest: returns structured GUI @ reference suggestions.

[POS]
File reference suggestion API. Resolves the current chat workspace and returns workspace, uploaded, generated and special references without exposing absolute paths.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from myrm_agent_harness.toolkits.storage.types import FilePurpose
from myrm_agent_harness.toolkits.filesystem_suggest import WorkspaceSuggestionOptions, rank_basename, suggest_workspace_paths
from pydantic import BaseModel, Field

from app.core.storage import files_service
from app.core.utils.errors import validation_error
from app.core.utils.response_utils import success_response
from app.services.chat.chat_service import ChatService

router = APIRouter()

ReferenceSource = Literal["workspace", "uploaded", "generated", "special"]
ReferenceType = Literal[
    "workspace_file",
    "workspace_folder",
    "uploaded_file",
    "generated_file",
    "git_diff",
    "git_staged",
    "url",
]
SuggestionKind = Literal["file", "directory", "reference"]


class ReferenceSuggestion(BaseModel):
    """Single selectable @ reference suggestion."""

    source: ReferenceSource
    reference_type: ReferenceType
    kind: SuggestionKind
    label: str
    basename: str
    directory: str = ""
    relative_path: str | None = None
    file_id: str | None = None
    description: str | None = None
    size: int | None = None
    score_tier: str
    score: int
    match_ranges: list[tuple[int, int]] = Field(default_factory=list)


class ReferenceSuggestResponse(BaseModel):
    """Response for @ reference suggestions."""

    results: list[ReferenceSuggestion]
    total: int


_SPECIAL_REFERENCES: tuple[ReferenceSuggestion, ...] = (
    ReferenceSuggestion(
        source="special",
        reference_type="git_staged",
        kind="reference",
        label="@staged",
        basename="@staged",
        description="Git staged changes",
        score_tier="prefix",
        score=1000,
    ),
    ReferenceSuggestion(
        source="special",
        reference_type="git_diff",
        kind="reference",
        label="@diff",
        basename="@diff",
        description="Git working tree changes",
        score_tier="prefix",
        score=990,
    ),
    ReferenceSuggestion(
        source="special",
        reference_type="workspace_folder",
        kind="directory",
        label="@folder:",
        basename="@folder:",
        description="Directory tree under workspace",
        score_tier="prefix",
        score=980,
    ),
    ReferenceSuggestion(
        source="special",
        reference_type="url",
        kind="reference",
        label="@url:",
        basename="@url:",
        description="Fetch webpage content",
        score_tier="prefix",
        score=970,
    ),
)


@router.get("/suggest", response_model=None)
async def suggest_references(
    chat_id: str = Query(..., description="Chat id used to resolve the workspace boundary"),
    q: str = Query("", description="@ mention query without the leading @"),
    limit: int = Query(30, ge=1, le=100),
    kind: Literal["any", "file", "directory"] = Query("any"),
    source: Literal["all", "workspace", "uploaded", "generated", "special"] = Query("all"),
) -> JSONResponse:
    """Suggest safe, structured references for the chat input."""

    query = q.strip()
    results: list[ReferenceSuggestion] = []

    if source in ("all", "special"):
        results.extend(_suggest_special(query))

    if source in ("all", "workspace"):
        workspace = await _resolve_workspace(chat_id)
        if workspace is not None:
            results.extend(_suggest_workspace(workspace, query, kind, limit))

    if kind != "directory" and source in ("all", "uploaded", "generated"):
        results.extend(await _suggest_stored_files(chat_id, query, source))

    results.sort(key=lambda item: (-item.score, item.source, item.label.lower()))
    bounded = results[:limit]
    return success_response(data=ReferenceSuggestResponse(results=bounded, total=len(bounded)).model_dump())


async def _resolve_workspace(chat_id: str) -> str | None:
    chat = await ChatService.get_chat_metadata(chat_id.strip())
    if chat is None:
        raise validation_error("Unknown chat_id")
    workspace = chat.workspace_dir or await ChatService.ensure_default_workspace_dir(chat_id.strip())
    if not workspace:
        return None
    resolved = os.path.realpath(os.path.expanduser(workspace))
    if not os.path.isdir(resolved):
        return None
    return resolved


def _suggest_special(query: str) -> list[ReferenceSuggestion]:
    bare_query = query.lower()
    if bare_query.startswith("@"):
        bare_query = bare_query[1:]
    matches: list[ReferenceSuggestion] = []
    for item in _SPECIAL_REFERENCES:
        needle = item.basename.removeprefix("@").removesuffix(":").lower()
        if not bare_query or needle.startswith(bare_query):
            matches.append(item)
    return matches


def _suggest_workspace(
    workspace: str,
    query: str,
    kind: Literal["any", "file", "directory"],
    limit: int,
) -> list[ReferenceSuggestion]:
    options = WorkspaceSuggestionOptions(limit=limit, kind=kind)
    suggestions = suggest_workspace_paths(workspace, query, options)
    results: list[ReferenceSuggestion] = []
    for item in suggestions:
        reference_type: ReferenceType = "workspace_folder" if item.kind == "directory" else "workspace_file"
        results.append(
            ReferenceSuggestion(
                source="workspace",
                reference_type=reference_type,
                kind=item.kind,
                label=item.basename,
                basename=item.basename,
                directory=item.directory,
                relative_path=item.relative_path,
                size=item.size,
                score_tier=item.score_tier,
                score=item.score,
                match_ranges=item.match_ranges,
            )
        )
    return results


async def _suggest_stored_files(
    chat_id: str,
    query: str,
    source: Literal["all", "workspace", "uploaded", "generated", "special"],
) -> list[ReferenceSuggestion]:
    purposes: list[FilePurpose]
    if source == "uploaded":
        purposes = [FilePurpose.UPLOAD]
    elif source == "generated":
        purposes = [FilePurpose.GENERATED]
    else:
        purposes = [FilePurpose.UPLOAD, FilePurpose.GENERATED]

    results: list[ReferenceSuggestion] = []
    for purpose in purposes:
        files = await files_service.list_files(purpose=purpose, include_expired=False)
        for file in files:
            if purpose == FilePurpose.GENERATED and file.source_chat_id and file.source_chat_id != chat_id:
                continue
            rank = rank_basename(file.filename, query)
            if rank is None:
                continue
            tier, score, ranges = rank
            basename = Path(file.filename).name
            results.append(
                ReferenceSuggestion(
                    source="uploaded" if purpose == FilePurpose.UPLOAD else "generated",
                    reference_type="uploaded_file" if purpose == FilePurpose.UPLOAD else "generated_file",
                    kind="file",
                    label=basename,
                    basename=basename,
                    directory="Uploaded files" if purpose == FilePurpose.UPLOAD else "Generated files",
                    file_id=file.id,
                    description=file.content_type,
                    size=file.size,
                    score_tier=tier,
                    score=score,
                    match_ranges=ranges,
                )
            )
    return results
