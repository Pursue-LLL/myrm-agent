"""Quadruple Retrieval Service wrapping harness pipeline for server endpoints.

[POS]
Server-side business service wrapping harness TaskGoalParser and
QuadrupleRetrievalOrchestrator. Strictly typed, zero Any, and imports
exclusively from harness memory top-level exports.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

from myrm_agent_harness.toolkits.memory import (
    ParsedTaskGoal,
    QuadrupleRetrievalOrchestrator,
    QuadrupleRetrievalReport,
    TaskGoalParser,
)

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ServiceMemoryRecord:
    """Concrete implementation of harness MemoryStoreItem protocol for server storage."""

    memory_id: str
    content: str
    subject: str
    predicate: str
    object_value: str
    metadata: Dict[str, str]


class QuadrupleRetrievalService:
    """Business service managing memory indexing and goal-driven 4-way retrieval."""

    def __init__(self) -> None:
        self._items: Dict[str, ServiceMemoryRecord] = {}
        self._parser = TaskGoalParser()
        self._orchestrator = QuadrupleRetrievalOrchestrator(parser=self._parser)

    def add_item(
        self,
        memory_id: str,
        content: str,
        subject: str,
        predicate: str,
        object_value: str,
        metadata: Optional[Dict[str, str]] = None,
    ) -> ServiceMemoryRecord:
        """Register or update a searchable memory record in the local store."""
        record = ServiceMemoryRecord(
            memory_id=memory_id,
            content=content,
            subject=subject,
            predicate=predicate,
            object_value=object_value,
            metadata=dict(metadata or {}),
        )
        self._items[memory_id] = record
        return record

    def parse_goal(
        self,
        query: str,
        scoped_filters: Optional[Dict[str, str]] = None,
    ) -> ParsedTaskGoal:
        """Deconstruct input query into intent and constraints."""
        return self._parser.parse_query(query, scoped_filters)

    def search(
        self,
        query: str,
        scoped_filters: Optional[Dict[str, str]] = None,
        top_k: int = 5,
    ) -> QuadrupleRetrievalReport:
        """Execute goal-driven quadruple parallel recall and reasoner reranking."""
        items_list = list(self._items.values())
        if scoped_filters:
            # Pre-filter by scoped metadata filters if required
            scoped_cube = scoped_filters.get("cube_id")
            if scoped_cube:
                items_list = [
                    item for item in items_list
                    if item.metadata.get("cube_id") == scoped_cube
                ]

        return self._orchestrator.search(
            query=query,
            items=items_list,
            top_k=top_k,
        )

    def list_items(self) -> List[ServiceMemoryRecord]:
        """List all indexed memory items."""
        return list(self._items.values())

    def clear(self) -> None:
        """Reset internal store state for test isolation."""
        self._items.clear()
        self._parser = TaskGoalParser()
        self._orchestrator = QuadrupleRetrievalOrchestrator(parser=self._parser)


_service_instance: Optional[QuadrupleRetrievalService] = None


def get_quadruple_retrieval_service() -> QuadrupleRetrievalService:
    """Retrieve singleton instance of QuadrupleRetrievalService."""
    global _service_instance
    if _service_instance is None:
        _service_instance = QuadrupleRetrievalService()
    return _service_instance
