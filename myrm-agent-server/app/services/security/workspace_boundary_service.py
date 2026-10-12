"""Workspace File Access Boundary & Link Resolution Service.

[INPUT]
- ResolvePathRequest, EvaluateAccessRequest, ParseMarkdownLinksRequest, DesktopRevealVerifyRequest.

[OUTPUT]
- PathResolutionDto, ParseMarkdownLinksResponse, DesktopRevealVerifyResponse.

[POS]
- Server security service. Wraps harness WorkspaceFileAccessGuard and ActualPathLinkResolver
  to protect host boundaries from path traversal and symlink escape attacks.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from myrm_agent_harness.core.security.workspace_boundary import (
    FileActionType,
    PathResolutionResult,
    WorkspaceBoundaryError,
    WorkspaceBoundaryPolicy,
    WorkspaceFileAccessGuard,
)

from app.schemas.workspace_boundary import (
    DesktopRevealVerifyRequest,
    DesktopRevealVerifyResponse,
    EvaluateAccessRequest,
    ParseMarkdownLinksRequest,
    ParseMarkdownLinksResponse,
    PathResolutionDto,
    ResolvePathRequest,
)

logger = logging.getLogger(__name__)


def _to_dto(res: PathResolutionResult) -> PathResolutionDto:
    return PathResolutionDto(
        raw_input=res.raw_input,
        resolved_physical_path=res.resolved_physical_path,
        workspace_root=res.workspace_root,
        verdict=res.verdict.value,
        is_inside_workspace=res.is_inside_workspace,
        is_regular_file=res.is_regular_file,
        can_launch=res.can_launch,
        can_reveal=res.can_reveal,
        can_read=res.can_read,
        error_message=res.error_message,
    )


class WorkspaceBoundaryService:
    """Service governing workspace file access boundaries and chat link resolution."""

    def __init__(self, default_roots: tuple[str, ...] | None = None) -> None:
        if default_roots:
            self._default_roots = default_roots
        else:
            self._default_roots = (str(Path(os.getcwd()).resolve()),)

    def _get_guard(self, custom_root: str | None = None) -> WorkspaceFileAccessGuard:
        roots = (custom_root,) if custom_root else self._default_roots
        policy = WorkspaceBoundaryPolicy(workspace_roots=roots)
        return WorkspaceFileAccessGuard(policy=policy)

    def resolve_path(self, req: ResolvePathRequest) -> PathResolutionDto:
        """Resolve link target to its physical path and evaluate containment."""
        guard = self._get_guard(req.custom_root)
        result = guard.resolver.resolve(req.target, custom_root=req.custom_root)
        return _to_dto(result)

    def evaluate_access(self, req: EvaluateAccessRequest) -> PathResolutionDto:
        """Evaluate whether a specific file action is authorized under workspace boundaries."""
        guard = self._get_guard(req.custom_root)
        try:
            action_type = FileActionType(req.action)
        except ValueError:
            action_type = FileActionType.LAUNCH_DEFAULT_APP

        result = guard.evaluate_access(req.target, action=action_type)
        return _to_dto(result)

    def parse_markdown_links(self, req: ParseMarkdownLinksRequest) -> ParseMarkdownLinksResponse:
        """Extract all file links from Markdown message and verify against workspace boundaries."""
        guard = self._get_guard(req.custom_root)
        results = guard.parse_and_resolve_markdown_links(req.markdown_text)
        dtos = [_to_dto(r) for r in results]
        return ParseMarkdownLinksResponse(total_links=len(dtos), links=dtos)

    def verify_desktop_reveal(self, req: DesktopRevealVerifyRequest) -> DesktopRevealVerifyResponse:
        """Verify and sanitize a file path before revealing in desktop file explorer."""
        guard = self._get_guard(req.custom_root)
        try:
            sanitized = guard.sanitize_for_desktop_reveal(req.target)
            return DesktopRevealVerifyResponse(allowed=True, sanitized_path=sanitized)
        except WorkspaceBoundaryError as err:
            return DesktopRevealVerifyResponse(
                allowed=False,
                sanitized_path="",
                error_message=str(err),
            )


_service_instance: WorkspaceBoundaryService | None = None


def get_workspace_boundary_service() -> WorkspaceBoundaryService:
    """Obtain or initialize singleton WorkspaceBoundaryService."""
    global _service_instance
    if _service_instance is None:
        _service_instance = WorkspaceBoundaryService()
    return _service_instance
