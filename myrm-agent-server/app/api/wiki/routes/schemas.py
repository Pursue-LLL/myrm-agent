"""[INPUT]
- （无跨模块依赖）

[OUTPUT]
- Wiki API 的请求/响应模型：查询与检索追踪、统计与维护、图谱与概念、目录树、内容变更、队列与修复。

[POS]
Wiki API 的子路由模块；由 app/api/wiki/router.py 组装到 /wiki 前缀下。
"""

import logging
from typing import TYPE_CHECKING, Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

router = APIRouter(tags=["wiki"])


class WikiQueryRequest(BaseModel):
    question: str = Field(..., min_length=1, description="Question to ask the wiki")
    mode: Literal["auto", "raw_claim"] = Field(
        default="auto",
        description="Retrieval mode: auto (default) or raw_claim (prioritize frontmatter claims)",
    )


class WikiSourceSnippet(BaseModel):
    path: str
    name: str
    snippet: str = ""
    section: str = ""
    level: str = "L2"
    claim_id: str = ""
    claim_text: str = ""
    evidence_path: str = ""
    line_range: str = ""
    claim_status: str = ""
    claim_confidence: float = 0.0
    snapshot_status: str = ""
    resource_uri: str = ""
    superseded_from_uri: str = ""
    hit_kind: str = "concept"
    asset_filename: str = ""


class WikiClaimEvidenceItem(BaseModel):
    kind: str = ""
    source_id: str = ""
    path: str = ""
    lines: str = ""
    weight: float = 1.0
    confidence: float = 0.0
    note: str = ""
    content_sha256: str = ""
    updated_at: str = ""
    snapshot_status: str = "missing"
    resource_uri: str = ""
    superseded_from_uri: str = ""


class WikiClaimItem(BaseModel):
    id: str
    text: str
    status: str = "unknown"
    confidence: float = 0.0
    updated_at: str = ""
    evidence: list[WikiClaimEvidenceItem] = Field(default_factory=list)


class WikiRetrievalTraceIndexHit(BaseModel):
    link_name: str
    summary: str
    score: float
    page_type: str = ""


class WikiRetrievalSeedTraceItem(BaseModel):
    concept_name: str
    score: float
    source: str


class WikiRetrievalTraceResponse(BaseModel):
    index_hits: list[WikiRetrievalTraceIndexHit] = Field(default_factory=list)
    seeds: list[WikiRetrievalSeedTraceItem] = Field(default_factory=list)
    sidecar_directories: list[str] = Field(default_factory=list)
    selected_concepts: list[str] = Field(default_factory=list)


class WikiQueryResponse(BaseModel):
    answer: str
    related_articles: list[str] = Field(default_factory=list)
    source_snippets: list[WikiSourceSnippet] = Field(default_factory=list)
    confidence_score: float = 0.0
    refused: bool = False
    retrieval_trace: WikiRetrievalTraceResponse | None = None


class WikiCompileResponse(BaseModel):
    """The compile has been handed to the background worker; its progress arrives on the ingest stream."""

    pending: int
    compile_run: "CompileRunResponse | None" = None


class CompileRunResponse(BaseModel):
    state: Literal["running", "paused"]
    pause_reason: str = ""
    primary_error_kind: str = ""
    phase: Literal["idle", "structure_survey", "semantic_compile", "postprocess"] = "idle"
    facet_count: int = 0
    warning_count: int = 0
    survey_skipped: bool = False


class WikiStructuralIssuesResponse(BaseModel):
    broken_links: int = 0
    invalid_frontmatter_types: int = 0
    provenance_gaps: int = 0
    scanned_concepts: int = 0


class WikiDedupStatsResponse(BaseModel):
    duplicate_groups_pending: int = 0
    compile_jobs_prevented: int = 0
    eligible_raw_count: int = 0
    excluded_raw_count: int = 0
    trashed_raw_count: int = 0
    blocks_compile: bool = False


class WikiAssetIndexStatsResponse(BaseModel):
    indexed: int = 0
    pending: int = 0
    failed: int = 0
    total_files: int = 0
    enabled: bool = False


class WikiMaintainStateResponse(BaseModel):
    last_run_at: str | None = None
    last_mode: str | None = None
    last_issues_found: int = 0
    last_issues_fixed: int = 0
    last_connections_discovered: int = 0
    last_duration_ms: int = 0
    last_skipped_reason: str | None = None


class WikiStatsResponse(BaseModel):
    total_concepts: int
    total_articles: int
    total_raw_files: int
    wiki_path: str
    vault_ready: bool
    legacy_migrated: bool
    cognitive_index_ready: bool = False
    cognitive_log_entries: int = 0
    cognitive_hot_updated_at: str | None = None
    synthesis_pending: int = 0
    obsidian_launch_available: bool = False
    vault_git_enabled: bool = False
    vault_git_initialized: bool = False
    vault_git_last_commit: str | None = None
    structural_issues: WikiStructuralIssuesResponse = Field(default_factory=WikiStructuralIssuesResponse)
    dedup_stats: WikiDedupStatsResponse = Field(default_factory=WikiDedupStatsResponse)
    maintain_state: WikiMaintainStateResponse = Field(default_factory=WikiMaintainStateResponse)
    asset_index: WikiAssetIndexStatsResponse = Field(default_factory=WikiAssetIndexStatsResponse)


class GraphNodeItem(BaseModel):
    id: str
    name: str
    group: int
    val: int = 1


class GraphEdgeItem(BaseModel):
    source: str
    target: str
    weight: float = 1.0


class WikiGraphResponse(BaseModel):
    nodes: list[GraphNodeItem]
    edges: list[GraphEdgeItem]


class ConceptLinkItem(BaseModel):
    name: str
    exists: bool


class ConceptBacklinkItem(ConceptLinkItem):
    context_snippet: str | None
    heading: str | None


class ConceptLinksResponse(BaseModel):
    concept_name: str
    outlinks: list[ConceptLinkItem]
    backlinks: list[ConceptBacklinkItem]
    outlinks_has_more: bool
    backlinks_has_more: bool


class WikiEditorSectionsResponse(BaseModel):
    compiled_truth: str = ""
    timeline: str = ""
    tags: list[str] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)


class ConceptResponse(BaseModel):
    name: str
    content: str
    content_hash: str = ""
    provenance: str | None = None
    source_chat: str | None = None
    source_message: str | None = None
    claims: list[WikiClaimItem] = Field(default_factory=list)
    editor_sections: WikiEditorSectionsResponse = Field(default_factory=WikiEditorSectionsResponse)


class ConceptListResponse(BaseModel):
    concepts: list[str]
    total: int
    has_more: bool


class TreeNode(BaseModel):
    id: str
    name: str
    is_dir: bool
    ingest_status: str | None = None
    children: list["TreeNode"] | None = None


class CreateFolderRequest(BaseModel):
    path: str = Field(..., min_length=1)


class MoveNodeRequest(BaseModel):
    source_path: str = Field(..., min_length=1)
    target_path: str = Field(..., min_length=1)


class DeleteFolderRequest(BaseModel):
    path: str = Field(..., min_length=1)


class WikiApplyClaimPatch(BaseModel):
    id: str = Field(..., min_length=1)
    text: str = Field(..., min_length=1)
    status: str = "unknown"
    confidence: float = 0.0
    updated_at: str = ""
    evidence: list[dict[str, object]] = Field(default_factory=list)


class WikiApplyRequestBody(BaseModel):
    op: Literal[
        "update_metadata",
        "patch_compiled_truth",
        "append_timeline",
        "create_note",
        "replace_full_document",
    ]
    concept_name: str = Field(..., min_length=1)
    compiled_truth: str = ""
    timeline_entry: str = ""
    content: str = ""
    body: str = ""
    tags: list[str] | None = None
    aliases: list[str] | None = None
    sources: list[str] | None = None
    claims: list[WikiApplyClaimPatch] = Field(default_factory=list)
    clear_confidence: bool = False
    page_type: str = "session"
    provenance: str = ""
    metadata: dict[str, object] = Field(default_factory=dict)
    canonical_id: str | None = None
    if_match: str | None = None


class WikiApplyResponse(BaseModel):
    success: bool
    op: str
    concept_name: str
    message: str
    created: bool = False
    appended: bool = False
    content_hash: str = ""
    staged_for_review: bool = False
    pending_edit_id: int | None = None


class WikiCompoundRequestBody(BaseModel):
    concept_name: str = Field(..., min_length=1)
    source_chat: str = Field(..., min_length=1)
    source_message: str = Field(..., min_length=1)


class WikiCompoundResponse(BaseModel):
    success: bool
    pending_edit_id: int
    concept_name: str
    message: str


class WikiDailyReviewRequestBody(BaseModel):
    text: str = Field(..., min_length=1, description="Daily review journal text (verbatim evidence)")
    title: str = Field("", max_length=120, description="Optional short title for the review file name")


class WikiDailyReviewResponse(BaseModel):
    success: bool
    raw_path: str
    enqueued: bool
    skipped: bool = False
    message: str


class WikiTemplateSeedRequest(BaseModel):
    force: bool = Field(False, description="Re-seed all four standard templates even if they exist")


class WikiTemplateSeedResponse(BaseModel):
    success: bool
    seeded: list[str]
    templates: list[str]


class QueueStatusResponse(BaseModel):
    stats: dict[str, int]
    pending_items: list[dict[str, object]]
    failed_items: list[dict[str, object]] = Field(default_factory=list)
    compile_run: CompileRunResponse | None = None


class PendingEditsResponse(BaseModel):
    stats: dict[str, int]
    pending_edits: list[dict[str, object]]


class OperationResult(BaseModel):
    success: bool
    message: str


class ApprovePendingEditRequest(BaseModel):
    modified_content: str | None = None


class RepairTypesResponse(BaseModel):
    success: bool
    files_scanned: int
    files_repaired: int
    files_skipped: int
    message: str


class RepairPublicationResponse(BaseModel):
    success: bool
    files_scanned: int
    files_repaired: int
    files_skipped: int
    files_skipped_intentional_drafts: int = 0
    reindexed: int
    message: str


class ReindexVectorsResponse(BaseModel):
    success: bool
    scanned: int
    reindexed: int
    concepts_reindexed: int
    sidecars_reindexed: int
    assets_indexed: int
    skipped_drafts: int
    failed: int
    errors: list[str] = Field(default_factory=list)
    message: str
