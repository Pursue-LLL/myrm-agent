"""Wiki 概念、目录树与概念详情路由。

[POS]
Wiki API 的子路由模块；由 app/api/wiki/router.py 组装到 /wiki 前缀下。
"""

import logging
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.wiki.archiver_dependency import get_scoped_wiki_archiver as _get_wiki_archiver
from app.api.wiki.routes import vault_effects
from app.api.wiki.routes.response_mappers import (
    _claims_to_response_items,
    _editor_sections_to_response,
    _str_or_none,
)
from app.api.wiki.routes.schemas import (
    ConceptBacklinkItem,
    ConceptLinkItem,
    ConceptLinksResponse,
    ConceptListResponse,
    ConceptResponse,
    CreateFolderRequest,
    MoveNodeRequest,
    OperationResult,
    TreeNode,
)
from app.services.wiki import MemoryToWikiArchiver

logger = logging.getLogger(__name__)


router = APIRouter(tags=["wiki"])


@router.get("/concepts", response_model=ConceptListResponse)
async def list_concepts(
    archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)],
    query: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> ConceptListResponse:
    """List or search concept names with pagination."""
    if query:
        # Use FTS5 indexer for fast search
        results = await archiver._query_engine._indexer.search(query, limit=limit + 1, offset=offset)
        concept_names = [name for name, _ in results]

        has_more = len(concept_names) > limit
        if has_more:
            concept_names = concept_names[:limit]

        return ConceptListResponse(concepts=concept_names, total=len(concept_names), has_more=has_more)
    else:
        paths = archiver._structure.list_concepts()
        concept_names = []
        for p in paths:
            try:
                rel = p.relative_to(archiver._structure.concepts_dir)
                concept_names.append(str(rel.with_suffix("")).replace("\\", "/"))
            except ValueError:
                concept_names.append(p.stem)

        total = len(concept_names)

        sliced = concept_names[offset : offset + limit]
        has_more = offset + limit < total

        return ConceptListResponse(concepts=sliced, total=total, has_more=has_more)


@router.get("/tree", response_model=list[TreeNode])
async def get_wiki_tree(
    archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)],
) -> list[TreeNode]:
    """Get the full directory tree of the wiki concepts."""
    from myrm_agent_harness.toolkits.wiki.maintenance.stale_summary import (
        collect_stale_raw_path_set,
        concept_uses_stale_sources,
    )

    concepts_dir = archiver._structure.concepts_dir
    stale_paths = collect_stale_raw_path_set(archiver._structure)

    def build_tree(dir_path: Path, rel_base: Path) -> list[TreeNode]:
        nodes: list[TreeNode] = []
        if not dir_path.exists():
            return nodes

        for item in sorted(dir_path.iterdir(), key=lambda x: (not x.is_dir(), x.name)):
            if item.is_dir():
                rel_id = str(item.relative_to(rel_base)).replace("\\", "/")
                children = build_tree(item, rel_base)
                child_statuses = [child.ingest_status for child in children if child.ingest_status]
                folder_status: str | None = None
                if any(status == "tracked-modified" for status in child_statuses):
                    folder_status = "tracked-modified"
                elif child_statuses:
                    folder_status = "tracked-clean"
                nodes.append(
                    TreeNode(
                        id=rel_id,
                        name=item.name,
                        is_dir=True,
                        ingest_status=folder_status,
                        children=children,
                    )
                )
            elif item.suffix == ".md":
                rel_id = str(item.relative_to(rel_base).with_suffix("")).replace("\\", "/")
                ingest_status: str | None = None
                if stale_paths:
                    try:
                        concept_content = item.read_text(encoding="utf-8")
                        ingest_status = (
                            "tracked-modified" if concept_uses_stale_sources(concept_content, stale_paths) else "tracked-clean"
                        )
                    except OSError:
                        ingest_status = None
                nodes.append(
                    TreeNode(
                        id=rel_id,
                        name=item.stem,
                        is_dir=False,
                        ingest_status=ingest_status,
                    )
                )
        return nodes

    return build_tree(concepts_dir, concepts_dir)


@router.get("/raw/tree", response_model=list[TreeNode])
async def get_wiki_raw_tree(
    archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)],
) -> list[TreeNode]:
    """Get the directory tree of raw source files with ingest status annotations."""
    from myrm_agent_harness.toolkits.wiki.maintenance.stale_summary import (
        collect_stale_raw_files,
        collect_stale_raw_path_set,
        resolve_raw_file_ingest_status,
    )

    raw_dir = archiver._structure.raw_dir
    summary = collect_stale_raw_files(archiver._structure)
    stale_paths = collect_stale_raw_path_set(archiver._structure)
    last_compile_time = summary.last_compile_time

    def build_raw_tree(dir_path: Path, rel_base: Path) -> list[TreeNode]:
        nodes: list[TreeNode] = []
        if not dir_path.exists():
            return nodes

        for item in sorted(dir_path.iterdir(), key=lambda x: (not x.is_dir(), x.name)):
            rel_path = item.relative_to(rel_base)
            rel_id = str(rel_path).replace("\\", "/")
            if item.is_dir():
                children = build_raw_tree(item, rel_base)
                child_statuses = [child.ingest_status for child in children if child.ingest_status]
                folder_status: str | None = None
                if any(status == "tracked-modified" for status in child_statuses):
                    folder_status = "tracked-modified"
                elif child_statuses:
                    folder_status = "tracked-clean"
                nodes.append(
                    TreeNode(
                        id=rel_id,
                        name=item.name,
                        is_dir=True,
                        ingest_status=folder_status,
                        children=children,
                    )
                )
            elif item.suffix == ".md":
                rel_id = str(rel_path.with_suffix("")).replace("\\", "/")
                stale_key = f"raw/{rel_id}.md"
                ingest_status = resolve_raw_file_ingest_status(
                    stale_key,
                    stale_paths=stale_paths,
                    last_compile_time=last_compile_time,
                )
                nodes.append(
                    TreeNode(
                        id=rel_id,
                        name=item.stem,
                        is_dir=False,
                        ingest_status=ingest_status,
                    )
                )
        return nodes

    return build_raw_tree(raw_dir, raw_dir)


@router.post("/tree/folder", response_model=OperationResult)
async def create_wiki_folder(
    request: CreateFolderRequest,
    archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)],
) -> OperationResult:
    """Create a new folder in the wiki concepts directory."""
    safe_path = archiver._structure._sanitize_path(request.path)
    folder_path = archiver._structure.concepts_dir / safe_path
    try:
        folder_path.mkdir(parents=True, exist_ok=True)
        return OperationResult(success=True, message=f"Folder {safe_path} created")
    except Exception as e:
        logger.error("Wiki folder creation failed: %s", e)
        raise HTTPException(status_code=500, detail="Folder creation failed") from e


@router.put("/tree/move", response_model=OperationResult)
async def move_wiki_node(
    request: MoveNodeRequest,
    archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)],
) -> OperationResult:
    """Move a file or folder and update relative links."""
    safe_source = archiver._structure._sanitize_path(request.source_path)
    safe_target = archiver._structure._sanitize_path(request.target_path)

    concepts_dir = archiver._structure.concepts_dir

    # Check if source is a file or dir
    source_file = concepts_dir / f"{safe_source}.md"
    source_dir = concepts_dir / safe_source

    if source_file.exists():
        old_path = source_file
        new_path = concepts_dir / f"{safe_target}.md"
    elif source_dir.exists() and source_dir.is_dir():
        old_path = source_dir
        new_path = concepts_dir / safe_target
    else:
        raise HTTPException(status_code=404, detail="Source not found")

    if new_path.exists():
        raise HTTPException(status_code=400, detail="Target already exists")

    try:
        new_path.parent.mkdir(parents=True, exist_ok=True)
        old_path.rename(new_path)

        # Refactor links
        from myrm_agent_harness.toolkits.wiki.core.refactor import LinkRefactorEngine

        engine = LinkRefactorEngine(concepts_dir)
        refactor_report = engine.refactor_links(old_path, new_path)

        from myrm_agent_harness.toolkits.wiki.pipeline.publication import (
            ConceptPathMapping,
            reindex_concepts_after_move,
        )

        mappings: list[ConceptPathMapping] = []
        if old_path.is_file():
            mappings.append(ConceptPathMapping(old_concept=safe_source, new_concept=safe_target))
        else:
            for md_file in new_path.rglob("*.md"):
                rel_new = md_file.relative_to(concepts_dir)
                concept_new = str(rel_new.with_suffix("")).replace("\\", "/")
                rel_to_new_dir = md_file.relative_to(new_path)
                old_md_file = old_path / rel_to_new_dir
                rel_old = old_md_file.relative_to(concepts_dir)
                concept_old = str(rel_old.with_suffix("")).replace("\\", "/")
                mappings.append(ConceptPathMapping(old_concept=concept_old, new_concept=concept_new))

        await reindex_concepts_after_move(
            archiver._structure,
            archiver._query_engine._indexer,
            mappings,
            modified_referrers=refactor_report.modified_concept_paths,
        )

        await vault_effects._after_wiki_vault_mutation(archiver, "move concept")
        return OperationResult(success=True, message=f"Moved successfully. Updated {refactor_report.updated_count} files.")
    except Exception as e:
        logger.error("Wiki node move failed: %s", e)
        raise HTTPException(status_code=500, detail="Move operation failed") from e


@router.delete("/tree/folder", response_model=OperationResult)
async def delete_wiki_folder(
    archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)],
    path: str = Query(..., min_length=1),
) -> OperationResult:
    """Safely delete a folder and clear all its files from the indexer."""
    try:
        deleted_count = await archiver._structure.delete_folder_safe(path, archiver._query_engine._indexer)
        await vault_effects._after_wiki_vault_mutation(archiver, "delete folder")
        return OperationResult(success=True, message=f"Folder deleted. Unindexed {deleted_count} files.")
    except Exception as e:
        logger.error("Wiki folder deletion failed: %s", e)
        raise HTTPException(status_code=500, detail="Folder deletion failed") from e


@router.get("/concepts/{name:path}/links", response_model=ConceptLinksResponse)
def get_concept_links(
    name: str,
    archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)],
) -> ConceptLinksResponse:
    """Fetch bidirectional links: outlinks, and backlinks with their context snippet and section."""
    try:
        res = archiver._query_engine._indexer.get_concept_links(name)
        return ConceptLinksResponse(
            concept_name=res["concept_name"],
            outlinks=[ConceptLinkItem(**item) for item in res["outlinks"]],
            backlinks=[ConceptBacklinkItem(**item) for item in res["backlinks"]],
            outlinks_has_more=res["outlinks_has_more"],
            backlinks_has_more=res["backlinks_has_more"],
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch concept links for '{name}': {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch concept links") from e


@router.get("/concepts/{name:path}", response_model=ConceptResponse)
async def get_concept(name: str, archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)]) -> ConceptResponse:
    """Get content of a specific concept."""
    path = archiver._structure.resolve_concept_file_path(name)
    if path is None or not path.exists():
        raise HTTPException(status_code=404, detail="Concept not found")
    content = path.read_text(encoding="utf-8")
    from myrm_agent_harness.toolkits.wiki.core.canonical_registry import (
        compute_page_lease_hash,
    )
    from myrm_agent_harness.toolkits.wiki.core.frontmatter_contract import (
        load_frontmatter_metadata,
    )

    metadata, _body = load_frontmatter_metadata(content)
    return ConceptResponse(
        name=name,
        content=content,
        content_hash=compute_page_lease_hash(content),
        provenance=str(metadata["provenance"]) if metadata.get("provenance") else None,
        source_chat=_str_or_none(metadata.get("source_chat")),
        source_message=_str_or_none(metadata.get("source_message")),
        claims=_claims_to_response_items(content, archiver._structure),
        editor_sections=_editor_sections_to_response(content),
    )
