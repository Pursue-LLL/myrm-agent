"""Pydantic DTO schemas for Workspace File Access Boundary Guard & Actual Path Link Resolver.

[INPUT]
- None.

[OUTPUT]
- Typed DTO models for path resolution requests/responses, access action evaluations,
  Markdown link parsing results, and desktop reveal verification.

[POS]
- Server schemas. Exposes typed contracts for workspace file access boundary protection.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class PathResolutionDto(BaseModel):
    """Result of resolving a file link or path reference."""

    model_config = ConfigDict(extra="forbid")

    raw_input: str = Field(..., description="Original raw link or path input")
    resolved_physical_path: str | None = Field(
        default=None, description="Canonical realpath on host disk if resolvable"
    )
    workspace_root: str = Field(..., description="Canonical workspace root path evaluated against")
    verdict: str = Field(..., description="ALLOWED, REFUSED_OUTSIDE_WORKSPACE, REFUSED_SYMLINK_ESCAPE, etc.")
    is_inside_workspace: bool = Field(..., description="Whether resolved target lies within workspace boundaries")
    is_regular_file: bool = Field(..., description="Whether resolved target is a regular file")
    can_launch: bool = Field(..., description="Whether file can safely be launched in default desktop app")
    can_reveal: bool = Field(..., description="Whether target can safely be revealed in OS file explorer")
    can_read: bool = Field(..., description="Whether content may safely be read by the agent")
    error_message: str = Field(default="", description="Reason for refusal if applicable")


class ResolvePathRequest(BaseModel):
    """Request payload to resolve a path or URI against workspace root."""

    model_config = ConfigDict(extra="forbid")

    target: str = Field(..., description="File path, relative path, or file:// URI to resolve")
    custom_root: str | None = Field(default=None, description="Optional custom workspace root folder")


class EvaluateAccessRequest(BaseModel):
    """Request payload to evaluate authorization for a specific file action."""

    model_config = ConfigDict(extra="forbid")

    target: str = Field(..., description="Target path or link")
    action: str = Field(
        default="LAUNCH_DEFAULT_APP",
        description="LAUNCH_DEFAULT_APP, REVEAL_IN_FOLDER, READ_CONTENT, or EDIT_CONTENT",
    )
    custom_root: str | None = Field(default=None, description="Optional custom workspace root")


class ParseMarkdownLinksRequest(BaseModel):
    """Request payload to extract and verify all file links from a Markdown message."""

    model_config = ConfigDict(extra="forbid")

    markdown_text: str = Field(..., description="Markdown text containing potential file links")
    custom_root: str | None = Field(default=None, description="Optional custom workspace root")


class ParseMarkdownLinksResponse(BaseModel):
    """Extracted file links from Markdown message with verified boundary resolutions."""

    model_config = ConfigDict(extra="forbid")

    total_links: int = Field(..., description="Total file links detected and resolved")
    links: list[PathResolutionDto] = Field(..., description="List of resolved link results")


class DesktopRevealVerifyRequest(BaseModel):
    """Request payload to sanitize and verify a path before invoking OS Reveal in Finder / Explorer."""

    model_config = ConfigDict(extra="forbid")

    target: str = Field(..., description="Path to reveal in desktop file manager")
    custom_root: str | None = Field(default=None, description="Optional custom workspace root")


class DesktopRevealVerifyResponse(BaseModel):
    """Verification and sanitization result for desktop file reveal."""

    model_config = ConfigDict(extra="forbid")

    allowed: bool = Field(..., description="Whether path is safe to reveal")
    sanitized_path: str = Field(..., description="Sanitized physical absolute path")
    error_message: str = Field(default="", description="Rejection reason if blocked")
