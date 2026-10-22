"""
[POS] app/services/agent/agent_hierarchy_service.py
[INPUT] collections, threading, time, app.schemas.agent_hierarchy
[OUTPUT] AgentHierarchyService, get_agent_hierarchy_service

Service orchestrating agent creation hierarchy, provenance tracking, cycle-breaking tree assembly, and ancestor tracing.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict

from app.schemas.agent_hierarchy import (
    AgentHierarchyNodeDTO,
    AgentHierarchyTreeResponseDTO,
    AgentProvenanceDTO,
    RegisterProvenanceRequestDTO,
)


class AgentHierarchyService:
    """Thread-safe coordinator for agent creation hierarchy trees and provenance ancestry."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._provenance_store: dict[str, AgentProvenanceDTO] = {}
        # In-memory agent registry fallback for tests / standalone usage
        self._agent_meta: dict[str, dict[str, str]] = {}

    def register_provenance(
        self,
        req: RegisterProvenanceRequestDTO,
    ) -> AgentProvenanceDTO:
        """Record or update provenance metadata for an agent."""
        with self._lock:
            # Self-parenting is invalid, treat as None
            parent_id = req.parent_agent_id if req.parent_agent_id != req.agent_id else None

            # Compute ancestry path if parent exists
            ancestry: list[str] = []
            if parent_id and parent_id in self._provenance_store:
                parent_prov = self._provenance_store[parent_id]
                ancestry = [*parent_prov.ancestry_path, parent_id]
            elif parent_id:
                ancestry = [parent_id]

            now = time.time()
            dto = AgentProvenanceDTO(
                agent_id=req.agent_id,
                creator_type=req.creator_type,
                creator_id=req.creator_id,
                parent_agent_id=parent_id,
                created_at=now,
                ancestry_path=ancestry,
            )
            self._provenance_store[req.agent_id] = dto
            return dto

    def get_provenance(self, agent_id: str) -> AgentProvenanceDTO | None:
        """Retrieve creation provenance record for a specific agent."""
        with self._lock:
            return self._provenance_store.get(agent_id)

    def record_agent_metadata(
        self,
        agent_id: str,
        name: str,
        description: str = "",
        avatar: str | None = None,
        agent_type: str = "individual",
    ) -> None:
        """Register display metadata for an agent."""
        with self._lock:
            self._agent_meta[agent_id] = {
                "name": name,
                "description": description,
                "avatar": avatar or "",
                "agent_type": agent_type,
            }

    def build_tree(
        self,
        explicit_agents: list[dict[str, str]] | None = None,
    ) -> AgentHierarchyTreeResponseDTO:
        """
        Assemble the creation hierarchy forest.
        Performs cycle detection to break circular parental links and promote orphan nodes to roots.
        """
        with self._lock:
            # 1. Merge provided agents or use stored metadata
            all_agents: dict[str, dict[str, str]] = dict(self._agent_meta)
            if explicit_agents:
                for a in explicit_agents:
                    aid = a.get("agent_id", "")
                    if aid:
                        all_agents[aid] = a

            if not all_agents and not self._provenance_store:
                return AgentHierarchyTreeResponseDTO(roots=[], total_nodes=0, max_depth=0)

            # Ensure every known provenance agent is in all_agents map
            for aid in self._provenance_store:
                if aid not in all_agents:
                    all_agents[aid] = {
                        "agent_id": aid,
                        "name": aid,
                        "description": "",
                        "avatar": "",
                        "agent_type": "individual",
                    }

            # 2. Cycle-detection & parent resolution
            # Adjacency: parent -> list of children
            parent_of: dict[str, str | None] = {}
            for aid in all_agents:
                prov = self._provenance_store.get(aid)
                p_id = prov.parent_agent_id if prov else None
                # If parent does not exist in all_agents, treat as orphan (root)
                if p_id and p_id not in all_agents:
                    p_id = None
                parent_of[aid] = p_id

            # Detect and break cycles
            sanitized_parent_of = self._break_cycles(parent_of)

            # 3. Build parent -> children map
            children_map: dict[str, list[str]] = defaultdict(list)
            roots: list[str] = []
            for aid, p_id in sanitized_parent_of.items():
                if p_id is None:
                    roots.append(aid)
                else:
                    children_map[p_id].append(aid)

            # Sort roots and children deterministically by name or ID
            roots.sort(key=lambda x: all_agents[x].get("name", x))
            for p_id in children_map:
                children_map[p_id].sort(key=lambda x: all_agents[x].get("name", x))

            # 4. Construct tree nodes recursively
            max_depth_tracker = [0]

            def construct_node(aid: str, current_depth: int) -> AgentHierarchyNodeDTO:
                if current_depth > max_depth_tracker[0]:
                    max_depth_tracker[0] = current_depth

                info = all_agents[aid]
                prov = self._provenance_store.get(aid)
                if prov is None:
                    prov = AgentProvenanceDTO(
                        agent_id=aid,
                        creator_type="user",
                        creator_id="system-default",
                        parent_agent_id=sanitized_parent_of.get(aid),
                        created_at=time.time(),
                        ancestry_path=[],
                    )

                child_nodes: list[AgentHierarchyNodeDTO] = []
                for child_id in children_map.get(aid, []):
                    child_nodes.append(construct_node(child_id, current_depth + 1))

                return AgentHierarchyNodeDTO(
                    agent_id=aid,
                    name=info.get("name", aid),
                    description=info.get("description", ""),
                    avatar=info.get("avatar") or None,
                    agent_type=info.get("agent_type", "individual"),
                    provenance=prov,
                    depth=current_depth,
                    children=child_nodes,
                )

            tree_roots = [construct_node(r_id, 0) for r_id in roots]

            return AgentHierarchyTreeResponseDTO(
                roots=tree_roots,
                total_nodes=len(all_agents),
                max_depth=max_depth_tracker[0],
            )

    @staticmethod
    def _break_cycles(parent_of: dict[str, str | None]) -> dict[str, str | None]:
        """Detect circular dependencies and sever the cycle by detaching circular parents."""
        clean_parents: dict[str, str | None] = dict(parent_of)

        for start_node in list(parent_of.keys()):
            visited: set[str] = set()
            curr: str | None = start_node

            while curr is not None:
                if curr in visited:
                    # Cycle detected, sever parent link of the current node to break cycle
                    clean_parents[curr] = None
                    break
                visited.add(curr)
                curr = clean_parents.get(curr)

        return clean_parents


_GLOBAL_HIERARCHY_SERVICE: AgentHierarchyService | None = None


def get_agent_hierarchy_service() -> AgentHierarchyService:
    """FastAPI dependency provider for AgentHierarchyService singleton."""
    global _GLOBAL_HIERARCHY_SERVICE
    if _GLOBAL_HIERARCHY_SERVICE is None:
        _GLOBAL_HIERARCHY_SERVICE = AgentHierarchyService()
    return _GLOBAL_HIERARCHY_SERVICE
