"""
[INPUT]: Turn injection manifest records, session IDs, turn IDs, and diff comparison requests.
[OUTPUT]: TurnContextInjectionManifestResponse, TurnProvenanceDiffResponse, and TokenBreakdownResponse.
[POS]: myrm-agent/myrm-agent-server/app/api/system/turn_context_provenance_api.py
"""

from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from myrm_agent_harness.observability.turn_context_provenance import (
    InjectionSourceKind,
    TurnContextChunk,
    TurnContextInjectionManifest,
    TurnContextManifestBuilder,
    TurnProvenanceDiffItem,
)

router = APIRouter(tags=["turn-context-provenance"])

# 内存单机存储（会话/轮次清单缓存，支持持久化集成）
_manifest_store: Dict[str, TurnContextInjectionManifest] = {}


# --- Pydantic Schemas ---

class ChunkPayload(BaseModel):
    source_id: str
    kind: str = "system_prompt"  # system_prompt | memory | skill | mcp_server | workspace_file | tool_schema
    content: str
    estimated_tokens: Optional[int] = None
    meta: Dict[str, str] = Field(default_factory=dict)


class RecordTurnManifestRequest(BaseModel):
    session_id: str
    turn_id: str
    model_snapshot_id: str = "claude-3-7-sonnet-20250219"
    chunks: List[ChunkPayload]


class TurnContextChunkResponse(BaseModel):
    chunk_id: str
    source_id: str
    kind: str
    content_sha256: str
    content_chars: int
    estimated_tokens: int
    order_index: int
    meta: Dict[str, str]


class TurnContextInjectionManifestResponse(BaseModel):
    session_id: str
    turn_id: str
    chunks: List[TurnContextChunkResponse]
    total_tokens: int
    total_chars: int
    model_snapshot_id: str
    created_at: str


class TurnProvenanceDiffItemResponse(BaseModel):
    source_id: str
    kind: str
    diff_type: str
    previous_sha256: Optional[str]
    current_sha256: Optional[str]
    token_delta: int


class TurnProvenanceDiffResponse(BaseModel):
    previous_turn_id: str
    current_turn_id: str
    diff_items: List[TurnProvenanceDiffItemResponse]
    total_token_delta: int


class SourceTokenBreakdownItem(BaseModel):
    kind: str
    tokens: int
    percentage: float
    chunk_count: int


class TurnTokenBreakdownResponse(BaseModel):
    session_id: str
    turn_id: str
    total_tokens: int
    breakdown_by_kind: Dict[str, SourceTokenBreakdownItem]


class CompareTurnsRequest(BaseModel):
    session_id: str
    previous_turn_id: str
    current_turn_id: str


# --- Converters ---

def _to_manifest_response(m: TurnContextInjectionManifest) -> TurnContextInjectionManifestResponse:
    chunk_responses = [
        TurnContextChunkResponse(
            chunk_id=c.chunk_id,
            source_id=c.source_id,
            kind=c.kind.value,
            content_sha256=c.content_sha256,
            content_chars=c.content_chars,
            estimated_tokens=c.estimated_tokens,
            order_index=c.order_index,
            meta=c.meta,
        )
        for c in m.chunks
    ]
    return TurnContextInjectionManifestResponse(
        session_id=m.session_id,
        turn_id=m.turn_id,
        chunks=chunk_responses,
        total_tokens=m.total_tokens,
        total_chars=m.total_chars,
        model_snapshot_id=m.model_snapshot_id,
        created_at=m.created_at,
    )


# --- Endpoints ---

@router.post(
    "/turn-context/manifest/record",
    response_model=TurnContextInjectionManifestResponse,
    summary="旁路上报并持久化单轮上下文注入来源清单与 SHA256 指纹快照",
)
def record_turn_manifest(payload: RecordTurnManifestRequest) -> TurnContextInjectionManifestResponse:
    builder = TurnContextManifestBuilder()
    for cp in payload.chunks:
        try:
            kind_enum = InjectionSourceKind(cp.kind)
        except ValueError:
            kind_enum = InjectionSourceKind.SYSTEM_PROMPT

        builder.add_chunk(
            source_id=cp.source_id,
            kind=kind_enum,
            content=cp.content,
            estimated_tokens=cp.estimated_tokens,
            meta=cp.meta,
        )

    manifest = builder.build(
        session_id=payload.session_id,
        turn_id=payload.turn_id,
        model_snapshot_id=payload.model_snapshot_id,
    )
    store_key = f"{payload.session_id}:{payload.turn_id}"
    _manifest_store[store_key] = manifest

    return _to_manifest_response(manifest)


@router.get(
    "/turn-context/manifest/{session_id}/{turn_id}",
    response_model=TurnContextInjectionManifestResponse,
    summary="获取指定会话指定轮次的上下文装配来源清单与 SHA256 指纹",
)
def get_turn_manifest(session_id: str, turn_id: str) -> TurnContextInjectionManifestResponse:
    store_key = f"{session_id}:{turn_id}"
    manifest = _manifest_store.get(store_key)
    if not manifest:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Turn context manifest not found for {store_key}",
        )
    return _to_manifest_response(manifest)


@router.post(
    "/turn-context/diff",
    response_model=TurnProvenanceDiffResponse,
    summary="跨轮次最小上下文注入差异比对，精准解释输出漂移与 Token 突增归因",
)
def diff_turn_manifests(payload: CompareTurnsRequest) -> TurnProvenanceDiffResponse:
    key_prev = f"{payload.session_id}:{payload.previous_turn_id}"
    key_curr = f"{payload.session_id}:{payload.current_turn_id}"

    prev_m = _manifest_store.get(key_prev)
    curr_m = _manifest_store.get(key_curr)

    if not prev_m:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Previous turn manifest not found: {key_prev}",
        )
    if not curr_m:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Current turn manifest not found: {key_curr}",
        )

    diff_items = TurnContextManifestBuilder.diff_manifests(prev_m, curr_m)
    total_delta = curr_m.total_tokens - prev_m.total_tokens

    diff_responses = [
        TurnProvenanceDiffItemResponse(
            source_id=d.source_id,
            kind=d.kind.value,
            diff_type=d.diff_type,
            previous_sha256=d.previous_sha256,
            current_sha256=d.current_sha256,
            token_delta=d.token_delta,
        )
        for d in diff_items
    ]

    return TurnProvenanceDiffResponse(
        previous_turn_id=payload.previous_turn_id,
        current_turn_id=payload.current_turn_id,
        diff_items=diff_responses,
        total_token_delta=total_delta,
    )


@router.get(
    "/turn-context/token-breakdown/{session_id}/{turn_id}",
    response_model=TurnTokenBreakdownResponse,
    summary="按来源分类 (System/Memory/Skill/MCP/Files) 聚合单轮 Token 占用与四色分解",
)
def get_turn_token_breakdown(session_id: str, turn_id: str) -> TurnTokenBreakdownResponse:
    store_key = f"{session_id}:{turn_id}"
    manifest = _manifest_store.get(store_key)
    if not manifest:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Turn manifest not found for {store_key}",
        )

    kind_sums: Dict[str, int] = {}
    kind_counts: Dict[str, int] = {}

    for c in manifest.chunks:
        k = c.kind.value
        kind_sums[k] = kind_sums.get(k, 0) + c.estimated_tokens
        kind_counts[k] = kind_counts.get(k, 0) + 1

    total = max(1, manifest.total_tokens)
    breakdown_map: Dict[str, SourceTokenBreakdownItem] = {}

    for k, tokens in kind_sums.items():
        pct = round((tokens / total) * 100.0, 1)
        breakdown_map[k] = SourceTokenBreakdownItem(
            kind=k,
            tokens=tokens,
            percentage=pct,
            chunk_count=kind_counts.get(k, 0),
        )

    return TurnTokenBreakdownResponse(
        session_id=session_id,
        turn_id=turn_id,
        total_tokens=manifest.total_tokens,
        breakdown_by_kind=breakdown_map,
    )
