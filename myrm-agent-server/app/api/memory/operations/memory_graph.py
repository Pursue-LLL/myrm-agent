"""Memory claim graph endpoint.

[INPUT]
app.api.memory.utils::get_crud_memory_manager (POS: 记忆管理器依赖，持有 Claim/Evidence 图存储)

[OUTPUT]
router: `GET /memory/command-center/graph` claim graph nodes, edges and ranked hubs.

[POS]
记忆知识图谱 API 操作层。对所有用户挂载：成长页（`/journey`）的「知识图谱」标签页读取它。
路径前缀为 `/command-center`；与 `command_center.py` 不同，它不受 `MYRM_MEMORY_LABS` 开关控制。
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from myrm_agent_harness.toolkits.memory import MemoryManager

from app.api.memory.utils import get_crud_memory_manager
from app.schemas.memory.command_center import (
    MemoryCommandGraphEdge,
    MemoryCommandGraphHubItem,
    MemoryCommandGraphNode,
    MemoryCommandGraphResponse,
    MemoryCommandGraphStats,
)

router = APIRouter(prefix="/command-center")


@router.get("/graph", response_model=MemoryCommandGraphResponse)
async def get_memory_graph(
    limit: int = 50,
    offset: int = 0,
    namespace: str | None = None,
    as_of_time: str | None = None,
    include_superseded: bool = False,
    memory_manager: MemoryManager = Depends(get_crud_memory_manager),
) -> MemoryCommandGraphResponse:
    """Return claim graph nodes and edges for visualization.

    Args:
        namespace: Filter nodes by primary_namespace property. None = show all.
        as_of_time: ISO-8601 temporal snapshot timestamp. If provided, returns relationships valid at this point in time.
        include_superseded: If True, includes superseded historical relationships.
    """

    if not memory_manager.has_graph or memory_manager._graph is None:
        return MemoryCommandGraphResponse(has_graph=False, graph_state="storage_disabled")

    graph = memory_manager._graph
    stats_raw = await graph.get_stats()
    if stats_raw.node_count == 0:
        return MemoryCommandGraphResponse(
            has_graph=True,
            graph_state="empty_knowledge",
            stats=MemoryCommandGraphStats(
                node_count=0,
                relationship_count=0,
                node_label_counts=stats_raw.node_label_counts,
                relationship_type_counts=stats_raw.relationship_type_counts,
            ),
        )

    safe_limit = min(max(limit, 1), 300)
    safe_offset = max(offset, 0)
    target_ns = namespace.strip() if namespace and namespace.strip() else None
    nodes_raw = await graph.list_nodes(limit=safe_limit, offset=safe_offset, namespace=target_ns)
    filtered_nodes = nodes_raw
    filtered_node_ids = {n.id for n in filtered_nodes}

    # Fetch induced subgraph edges for current nodes, preventing orphan nodes & truncation
    if filtered_node_ids:
        rels_raw = await graph.list_relationships(
            limit=safe_limit * 5,
            offset=0,
            node_ids=list(filtered_node_ids),
            as_of_time=as_of_time,
            include_superseded=include_superseded,
        )
    else:
        rels_raw = []

    # Degree and conflict tracking for dual-view ranking
    in_degrees: dict[str, int] = {}
    out_degrees: dict[str, int] = {}
    supported_counts: dict[str, int] = {}
    contradicted_counts: dict[str, int] = {}

    edges: list[MemoryCommandGraphEdge] = []
    for r in rels_raw:
        if r.start_id in filtered_node_ids and r.end_id in filtered_node_ids:
            edges.append(
                MemoryCommandGraphEdge(
                    id=r.id,
                    source=r.start_id,
                    target=r.end_id,
                    rel_type=r.rel_type,
                    properties=r.properties,
                    valid_from=r.valid_from,
                    valid_until=r.valid_until,
                    superseded_by=r.superseded_by,
                    supersedes_id=r.supersedes_id,
                )
            )
            out_degrees[r.start_id] = out_degrees.get(r.start_id, 0) + 1
            in_degrees[r.end_id] = in_degrees.get(r.end_id, 0) + 1
            if r.rel_type == "SUPPORTED_BY":
                supported_counts[r.start_id] = supported_counts.get(r.start_id, 0) + 1
            elif r.rel_type == "CONTRADICTED_BY":
                contradicted_counts[r.start_id] = contradicted_counts.get(r.start_id, 0) + 1

    # Extract ranked hubs (Claims prioritized by degree centrality and conflicts)
    ranked_hubs: list[MemoryCommandGraphHubItem] = []
    for n in filtered_nodes:
        in_deg = in_degrees.get(n.id, 0)
        out_deg = out_degrees.get(n.id, 0)
        total_deg = in_deg + out_deg
        supp_cnt = supported_counts.get(n.id, 0)
        contra_cnt = contradicted_counts.get(n.id, 0)

        # Label extraction
        display_label = n.labels[0] if n.labels else "Claim"
        props = n.properties or {}
        snippet = str(props.get("content") or props.get("name") or props.get("quote_snippet") or n.id[:12])
        if len(snippet) > 80:
            snippet = f"{snippet[:77]}..."

        ranked_hubs.append(
            MemoryCommandGraphHubItem(
                id=n.id,
                label=display_label,
                snippet=snippet,
                primary_namespace=str(props.get("primary_namespace", "")) or None,
                degree=total_deg,
                in_degree=in_deg,
                out_degree=out_deg,
                supported_count=supp_cnt,
                contradicted_count=contra_cnt,
                has_conflict=contra_cnt > 0,
            )
        )

    # Sort: conflicted hotspots first, then by total degree descending
    ranked_hubs.sort(key=lambda h: (h.contradicted_count > 0, h.degree, h.supported_count), reverse=True)

    nodes = [MemoryCommandGraphNode(id=n.id, labels=n.labels, properties=n.properties) for n in filtered_nodes]
    stats = MemoryCommandGraphStats(
        node_count=len(nodes),
        relationship_count=len(edges),
        node_label_counts=stats_raw.node_label_counts,
        relationship_type_counts=stats_raw.relationship_type_counts,
    )

    graph_state: Literal["ready", "storage_disabled", "empty_knowledge", "sparse_islands"] = "ready"
    if len(nodes) > 0 and len(edges) == 0:
        graph_state = "sparse_islands"

    return MemoryCommandGraphResponse(
        nodes=nodes,
        edges=edges,
        stats=stats,
        ranked_hubs=ranked_hubs[:30],
        graph_state=graph_state,
        has_graph=True,
    )
