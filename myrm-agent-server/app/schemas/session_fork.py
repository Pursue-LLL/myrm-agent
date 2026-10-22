"""Pydantic V2 schemas for Pi Harness v2 Deterministic Subagent Session Fork Primitive (Item 51).

[INPUT]
- ForkChildSessionRequest, DeriveChildIdRequest.

[OUTPUT]
- ForkedSessionNodeDTO, ChildSessionLinkDTO, ForkResultDTO, DeriveChildIdResponse,
  ChildSessionListResponse.

[POS]
- Server-side typed DTO schemas for deterministic session fork and safe replay reattach.
"""

from __future__ import annotations

import enum

from pydantic import BaseModel, ConfigDict, Field

PrimitiveValue = str | int | float | bool | None


class ForkScopeEnum(enum.StrEnum):
    """Scope selector for entry duplication during session fork."""

    BRANCH = "branch"
    TREE = "tree"


class ForkedSessionNodeDTO(BaseModel):
    """DTO representing an entry / node within a forked session."""

    model_config = ConfigDict(frozen=True)

    node_id: str = Field(..., description="Unique node identifier")
    parent_id: str | None = Field(default=None, description="Parent node identifier")
    node_type: str = Field(..., description="Type of node, e.g. message, root, tool_result")
    content: str = Field(..., description="Content payload of the node")
    created_at: float = Field(..., description="Node creation epoch timestamp")
    metadata: dict[str, PrimitiveValue] = Field(default_factory=dict, description="Metadata dictionary")


class ChildSessionLinkDTO(BaseModel):
    """DTO representing deterministic linkage and replay tracking between parent and child."""

    model_config = ConfigDict(frozen=True)

    child_session_id: str = Field(..., description="Deterministically derived child session identifier")
    parent_session_id: str = Field(..., description="Parent session identifier")
    tool_call_id: str = Field(..., description="Invocation tool call ID")
    fork_scope: ForkScopeEnum = Field(..., description="Branch or tree scope")
    created_at: float = Field(..., description="Initial spawn epoch timestamp")
    reattach_count: int = Field(default=0, description="Number of times safely reattached upon replay")
    last_attached_at: float = Field(..., description="Last attachment timestamp")


class ForkResultDTO(BaseModel):
    """DTO returned upon executing fork or safe replay reattachment."""

    model_config = ConfigDict(frozen=True)

    child_session_id: str = Field(..., description="Derived child session identifier")
    parent_session_id: str = Field(..., description="Parent session identifier")
    tool_call_id: str = Field(..., description="Tool call identifier")
    is_reattached: bool = Field(..., description="True if safely reattached without re-spawning a twin")
    fork_scope: ForkScopeEnum = Field(..., description="Applied scope: branch or tree")
    copied_nodes_count: int = Field(..., description="Count of historical nodes copied into child")
    root_node_id: str = Field(..., description="Root node ID of the forked child")
    leaf_node_id: str = Field(..., description="Current leaf node ID of the forked child")


class ForkChildSessionRequest(BaseModel):
    """Request to fork a new child session or reattach to existing one."""

    parent_session_id: str = Field(..., min_length=1, max_length=128, description="Parent session ID")
    tool_call_id: str = Field(..., min_length=1, max_length=128, description="Tool invocation call ID")
    scope: ForkScopeEnum = Field(default=ForkScopeEnum.BRANCH, description="branch or tree scope")
    parent_nodes: list[ForkedSessionNodeDTO] = Field(
        default_factory=list,
        description="Optional list of parent nodes to fork from",
    )
    target_leaf_id: str | None = Field(default=None, description="Optional target leaf to trace branch from")


class DeriveChildIdRequest(BaseModel):
    """Request to compute deterministic child session ID purely without forking."""

    parent_session_id: str = Field(..., min_length=1, max_length=128, description="Parent session ID")
    tool_call_id: str = Field(..., min_length=1, max_length=128, description="Tool invocation call ID")


class DeriveChildIdResponse(BaseModel):
    """Response containing deterministically derived child ID."""

    model_config = ConfigDict(frozen=True)

    child_session_id: str = Field(..., description="Derived child session ID")
    parent_session_id: str = Field(..., description="Parent session ID")
    tool_call_id: str = Field(..., description="Tool call ID")


class ChildSessionListResponse(BaseModel):
    """Response listing all child sessions deterministically forked by a parent."""

    model_config = ConfigDict(frozen=True)

    parent_session_id: str = Field(..., description="Parent session ID")
    children: list[ChildSessionLinkDTO] = Field(..., description="List of linked child sessions")
    total_children: int = Field(..., description="Total count of children")
