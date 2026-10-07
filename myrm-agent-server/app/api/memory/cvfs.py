"""[POS]: app/api/memory/cvfs.py
[INPUT]: HTTP requests for Context Virtual File System browsing, reading, writing, and searching.
[OUTPUT]: FastAPI APIRouter endpoints delivering deterministic context exploration and tree navigation.
"""

from fastapi import APIRouter, Depends, HTTPException
from myrm_agent_harness.toolkits.memory import (
    ContextVirtualFileSystem,
    CVFSProtocolError,
)

from app.schemas.cvfs import (
    VFSFindRequest,
    VFSFindResponse,
    VFSMkdirRequest,
    VFSNodeResponse,
    VFSReadResponse,
    VFSTreeResponse,
    VFSWriteRequest,
)
from app.services.memory.cvfs import get_context_vfs

router = APIRouter(prefix="/cvfs", tags=["memory_cvfs"])


@router.get("/ls", response_model=list[VFSNodeResponse])
def list_vfs_directory(
    uri: str = "ctx://",
    vfs: ContextVirtualFileSystem = Depends(get_context_vfs),
) -> list[VFSNodeResponse]:
    """List direct child nodes under specified Context Virtual File System path."""
    try:
        nodes = vfs.ls(uri=uri)
    except CVFSProtocolError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return [
        VFSNodeResponse(
            uri=n.uri,
            parent_uri=n.parent_uri,
            name=n.name,
            node_type=n.node_type.value,
            size_bytes=n.size_bytes,
            metadata=n.metadata,
            created_at_epoch=n.created_at_epoch,
            updated_at_epoch=n.updated_at_epoch,
        )
        for n in nodes
    ]


@router.get("/tree", response_model=VFSTreeResponse)
def get_vfs_tree(
    uri: str = "ctx://",
    max_depth: int = 3,
    vfs: ContextVirtualFileSystem = Depends(get_context_vfs),
) -> VFSTreeResponse:
    """Render visual POSIX ASCII tree representation of Context Virtual File System."""
    try:
        res = vfs.tree(uri=uri, max_depth=max_depth)
    except CVFSProtocolError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return VFSTreeResponse(
        root_uri=res.root_uri,
        total_nodes=res.total_nodes,
        rendered_tree=res.rendered_tree,
    )


@router.get("/read", response_model=VFSReadResponse)
def read_vfs_file(
    uri: str,
    offset: int = 0,
    limit: int = 4000,
    vfs: ContextVirtualFileSystem = Depends(get_context_vfs),
) -> VFSReadResponse:
    """Deterministically read content snippet from target virtual file."""
    try:
        res = vfs.read(uri=uri, offset=offset, limit=limit)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except IsADirectoryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except CVFSProtocolError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return VFSReadResponse(
        uri=res.uri,
        content=res.content,
        size_bytes=res.size_bytes,
        offset=res.offset,
        limit=res.limit,
        has_more=res.has_more,
    )


@router.post("/write", response_model=VFSNodeResponse)
def write_vfs_file(
    req: VFSWriteRequest,
    vfs: ContextVirtualFileSystem = Depends(get_context_vfs),
) -> VFSNodeResponse:
    """Write or update a context asset in virtual file system."""
    try:
        node = vfs.write(uri=req.uri, content=req.content, metadata=req.metadata)
    except CVFSProtocolError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return VFSNodeResponse(
        uri=node.uri,
        parent_uri=node.parent_uri,
        name=node.name,
        node_type=node.node_type.value,
        size_bytes=node.size_bytes,
        metadata=node.metadata,
        created_at_epoch=node.created_at_epoch,
        updated_at_epoch=node.updated_at_epoch,
    )


@router.post("/mkdir", response_model=VFSNodeResponse)
def create_vfs_directory(
    req: VFSMkdirRequest,
    vfs: ContextVirtualFileSystem = Depends(get_context_vfs),
) -> VFSNodeResponse:
    """Explicitly create a virtual directory hierarchy."""
    try:
        node = vfs.mkdir(uri=req.uri, metadata=req.metadata)
    except CVFSProtocolError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return VFSNodeResponse(
        uri=node.uri,
        parent_uri=node.parent_uri,
        name=node.name,
        node_type=node.node_type.value,
        size_bytes=node.size_bytes,
        metadata=node.metadata,
        created_at_epoch=node.created_at_epoch,
        updated_at_epoch=node.updated_at_epoch,
    )


@router.post("/find", response_model=VFSFindResponse)
def find_vfs_nodes(
    req: VFSFindRequest,
    vfs: ContextVirtualFileSystem = Depends(get_context_vfs),
) -> VFSFindResponse:
    """Find context nodes matching keyword in name or content."""
    try:
        matches = vfs.find(keyword=req.keyword, prefix_uri=req.prefix_uri)
    except CVFSProtocolError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    node_list = [
        VFSNodeResponse(
            uri=m.uri,
            parent_uri=m.parent_uri,
            name=m.name,
            node_type=m.node_type.value,
            size_bytes=m.size_bytes,
            metadata=m.metadata,
            created_at_epoch=m.created_at_epoch,
            updated_at_epoch=m.updated_at_epoch,
        )
        for m in matches
    ]
    return VFSFindResponse(matches=node_list, total=len(node_list))


@router.delete("/node")
def delete_vfs_node(
    uri: str,
    vfs: ContextVirtualFileSystem = Depends(get_context_vfs),
) -> dict[str, str | bool]:
    """Recursively delete target virtual node and its descendants."""
    try:
        deleted = vfs.delete(uri=uri)
    except CVFSProtocolError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {"uri": uri, "deleted": deleted}
