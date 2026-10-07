"""[POS]: app/schemas/cvfs.py
[INPUT]: Request and response parameters for Context Virtual File System exploration and I/O.
[OUTPUT]: Strongly typed Pydantic models for VFS nodes, tree hierarchy, file reads, and searches.
"""

from pydantic import BaseModel, Field


class VFSNodeResponse(BaseModel):
    """Metadata representation of a virtual file system node."""

    uri: str = Field(..., description="Canonical ctx:// URI")
    parent_uri: str = Field(..., description="Parent directory URI")
    name: str = Field(..., description="File or directory name")
    node_type: str = Field(..., description="Node type: directory or file")
    size_bytes: int = Field(default=0, ge=0, description="Size in bytes")
    metadata: dict[str, str] = Field(default_factory=dict, description="Metadata tags")
    created_at_epoch: float = Field(..., description="Creation epoch timestamp in seconds")
    updated_at_epoch: float = Field(..., description="Update epoch timestamp in seconds")


class VFSReadResponse(BaseModel):
    """File content read response with slicing pagination."""

    uri: str = Field(..., description="Canonical ctx:// URI")
    content: str = Field(..., description="Sliced text payload")
    size_bytes: int = Field(..., description="Total file size in bytes")
    offset: int = Field(default=0, ge=0, description="Read offset")
    limit: int = Field(default=4000, ge=1, description="Read limit")
    has_more: bool = Field(default=False, description="Whether more content is available")


class VFSTreeResponse(BaseModel):
    """Visual ASCII directory tree hierarchy and node count."""

    root_uri: str = Field(..., description="Root URI of tree exploration")
    total_nodes: int = Field(default=0, ge=0, description="Total nodes traversed")
    rendered_tree: str = Field(..., description="Visual ASCII tree string")


class VFSWriteRequest(BaseModel):
    """Request payload to write or update a virtual file."""

    uri: str = Field(..., description="Target canonical ctx:// URI")
    content: str = Field(..., description="Text payload to store")
    metadata: dict[str, str] = Field(default_factory=dict, description="Contextual metadata annotations")


class VFSMkdirRequest(BaseModel):
    """Request payload to create a virtual directory."""

    uri: str = Field(..., description="Target directory ctx:// URI")
    metadata: dict[str, str] = Field(default_factory=dict, description="Directory metadata annotations")


class VFSFindRequest(BaseModel):
    """Request payload to search virtual nodes."""

    keyword: str = Field(..., description="Search keyword in name, content, or URI")
    prefix_uri: str = Field(default="ctx://", description="Prefix URI boundary for search")
    node_type: str | None = Field(default=None, description="Optional node type filter: directory or file")


class VFSFindResponse(BaseModel):
    """Search matches response."""

    matches: list[VFSNodeResponse] = Field(default_factory=list, description="Matched VFS nodes")
    total: int = Field(..., description="Total matched node count")


class VFSSubtreeStatsResponse(BaseModel):
    """Aggregated volume and structural statistics for a VFS subtree."""

    root_uri: str = Field(..., description="Target subtree root URI")
    total_nodes: int = Field(default=0, ge=0, description="Total node count in subtree")
    file_count: int = Field(default=0, ge=0, description="Total file count in subtree")
    directory_count: int = Field(default=0, ge=0, description="Total directory count in subtree")
    total_bytes: int = Field(default=0, ge=0, description="Total storage bytes across files")


class VFSMountRequest(BaseModel):
    """Request payload to mount an external context provider."""

    mount_point: str = Field(..., description="Target mount point URI")
    description: str = Field(default="", description="Mount description")
    is_read_only: bool = Field(default=True, description="Whether mount is strictly read-only")


class VFSMountResponse(BaseModel):
    """Response descriptor for a mounted context provider."""

    mount_point: str = Field(..., description="Target mount point URI")
    description: str = Field(default="", description="Mount description")
    is_read_only: bool = Field(default=True, description="Whether mount is strictly read-only")
    mounted_at_epoch: float = Field(..., description="Timestamp of mounting in epoch seconds")

