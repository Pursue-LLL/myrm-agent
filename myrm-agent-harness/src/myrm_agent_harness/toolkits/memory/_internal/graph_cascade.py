"""Cascade graph cleanup for derived nodes upon memory deletion.

[INPUT]
- logging::logging (POS: Python 标准日志库)
- toolkits.memory.protocols.graph::GraphStoreProtocol
  (POS: 图存储抽象协议层)

[OUTPUT]
- cascade_clean_derived_graph_nodes: awaitable removal of graph nodes derived from a
  deleted memory id
- drop_chat_claims: awaitable removal of the evidence a deleted chat's digests produced and of
  every claim last worded from one of them

[POS]
Internal consistency guard of the memory toolkit. Deleting a memory must not leave derived
graph nodes orphaned, which would let the graph surface facts whose source no longer exists.
Receives the store through the protocol so no concrete backend is imported here.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.toolkits.memory.protocols.graph import GraphStoreProtocol

logger = logging.getLogger(__name__)

_PAGE_SIZE = 200


async def cascade_clean_derived_graph_nodes(graph: GraphStoreProtocol | None, memory_id: str) -> None:
    """Remove Claim Graph nodes derived from a deleted/archived memory.

    Evidence nodes carry ``source_memory_id`` pointing back to the original
    vector document.  Claim nodes track ``latest_source_memory_id``.  When
    the original memory is removed, the derived Evidence must be deleted and
    Claim's ``evidence_count`` decremented; a Claim with zero remaining
    Evidence is deleted entirely.
    """
    if graph is None:
        return
    try:
        await graph.delete_subgraph(memory_id)
    except Exception as exc:
        logger.warning("Graph subgraph cleanup failed for %s: %s", memory_id, exc)

    try:
        evidence_nodes = await graph.find_nodes(
            ["Evidence"],
            {"source_memory_id": memory_id},
        )
    except Exception as exc:
        logger.warning("Graph evidence lookup failed for %s: %s", memory_id, exc)
        return

    for evidence in evidence_nodes:
        try:
            await graph.delete_subgraph(evidence.id)
        except Exception as exc:
            logger.warning("Graph evidence delete failed for %s: %s", evidence.id, exc)

    try:
        claim_nodes = await graph.find_nodes(
            ["Claim"],
            {"latest_source_memory_id": memory_id},
        )
    except Exception as exc:
        logger.warning("Graph claim lookup failed for %s: %s", memory_id, exc)
        return

    for claim in claim_nodes:
        evidence_count = int(claim.properties.get("evidence_count", 0))
        if evidence_count <= 1:
            try:
                await graph.delete_subgraph(claim.id)
            except Exception as exc:
                logger.warning("Graph claim delete failed for %s: %s", claim.id, exc)
        else:
            try:
                await graph.update_node_properties(
                    claim.id,
                    {"evidence_count": max(0, evidence_count - 1)},
                )
            except Exception as exc:
                logger.warning("Graph claim update failed for %s: %s", claim.id, exc)


async def drop_chat_claims(
    graph: GraphStoreProtocol | None, chat_id: str, *, namespaces: list[str] | None = None
) -> None:
    """Delete the evidence a chat's digests produced and every claim last worded from one of them.

    A claim carries the wording of the digest that updated it last, so a claim last updated from this chat's digest goes
    whole, even when other chats' digests also back it: what a deleted chat said must not live on in the graph. A claim
    worded from another chat keeps its text; only its evidence count still includes this chat. ``namespaces`` limits the
    sweep to the scopes the caller owns, ``None`` covers every scope. A graph failure is logged and skipped so the
    purge it belongs to still deletes the memories.
    """
    if graph is None:
        return
    for namespace in (None,) if namespaces is None else namespaces:
        filters: dict[str, str | int | float | bool] = {"source_chat_id": chat_id}
        if namespace is not None:
            filters["primary_namespace"] = namespace
        try:
            await _drop_evidence_and_claims(graph, filters)
        except Exception as exc:
            logger.warning("Graph cleanup failed for chat %s: %s", chat_id, exc)


async def _drop_evidence_and_claims(graph: GraphStoreProtocol, filters: dict[str, str | int | float | bool]) -> None:
    """Delete every evidence node matching ``filters`` and the claims last worded from their digests."""
    handled: set[str] = set()
    while True:
        batch = [
            node for node in await graph.find_nodes(["Evidence"], filters, limit=_PAGE_SIZE) if node.id not in handled
        ]
        if not batch:
            return
        for evidence in batch:
            handled.add(evidence.id)
            digest_id = evidence.properties.get("source_memory_id")
            if isinstance(digest_id, str):
                for claim in await graph.find_nodes(["Claim"], {"latest_source_memory_id": digest_id}):
                    await graph.delete_subgraph(claim.id)
            await graph.delete_subgraph(evidence.id)
